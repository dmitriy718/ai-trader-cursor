"""ML price prediction using TensorFlow Lite."""

import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any

# Try tflite-runtime first (for ARM64/Raspberry Pi), fallback to tensorflow
try:
    from tflite_runtime.interpreter import Interpreter as TFLiteInterpreter
    TFLITE_AVAILABLE = True
except ImportError:
    try:
        import tensorflow as tf
        TFLiteInterpreter = tf.lite.Interpreter
        TFLITE_AVAILABLE = True
    except ImportError:
        TFLiteInterpreter = None
        TFLITE_AVAILABLE = False

from ..core.logger import setup_logger
from ..storage.models import Kline


class PricePredictor:
    """Price prediction using TensorFlow Lite model."""
    
    def __init__(self, model_path: str):
        """
        Initialize price predictor.
        
        Args:
            model_path: Path to TensorFlow Lite model file
        """
        self.model_path = model_path
        self.logger = setup_logger("PricePredictor")
        self.interpreter: Optional[TFLiteInterpreter] = None
        self.input_details = None
        self.output_details = None
        self._load_model()
    
    def _load_model(self):
        """Load TensorFlow Lite model."""
        if not TFLITE_AVAILABLE:
            self.logger.warning("TensorFlow Lite not available, using dummy model")
            self._create_dummy_model()
            return
        
        try:
            if not Path(self.model_path).exists():
                self.logger.warning(f"Model file not found: {self.model_path}")
                self.logger.info("Creating a dummy model for demonstration")
                self._create_dummy_model()
                return
            
            # For Docker volumes on ARM64, copy model to /tmp to avoid mmap errors
            import shutil
            tmp_model = Path("/tmp/model.tflite")
            try:
                shutil.copy2(self.model_path, tmp_model)
                model_path_to_use = str(tmp_model)
            except Exception:
                # If copy fails, use original path
                model_path_to_use = self.model_path
            
            self.interpreter = TFLiteInterpreter(model_path=model_path_to_use)
            self.interpreter.allocate_tensors()
            
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            
            self.logger.info("ML model loaded successfully")
        except Exception as e:
            self.logger.error(f"Error loading model: {e}")
            self.logger.info("Falling back to dummy model")
            self._create_dummy_model()
    
    def _create_dummy_model(self):
        """Create a dummy model for demonstration purposes."""
        # This is a placeholder - in production, you'd train a real model
        self.interpreter = None
        self.logger.info("Using dummy prediction model")
    
    def prepare_features(self, klines: list[Kline], window_size: int = 60) -> np.ndarray:
        """
        Prepare features from klines for model input.
        
        Args:
            klines: List of kline data
            window_size: Number of candles to use as input
        
        Returns:
            Feature array
        """
        if len(klines) < window_size:
            # Pad with last value if not enough data
            klines = [klines[0]] * (window_size - len(klines)) + klines
        
        # Use last window_size klines
        recent_klines = klines[-window_size:]
        
        # Extract features: OHLCV normalized
        features = []
        prices = [k.close_price for k in recent_klines]
        volumes = [k.volume for k in recent_klines]
        
        # Normalize prices (use first price as reference)
        base_price = prices[0] if prices[0] > 0 else 1.0
        normalized_prices = [(p / base_price - 1.0) * 100 for p in prices]
        
        # Normalize volumes
        base_volume = volumes[0] if volumes[0] > 0 else 1.0
        normalized_volumes = [(v / base_volume - 1.0) * 100 for v in volumes]
        
        # Create feature vector: [normalized_prices, normalized_volumes]
        feature_vector = normalized_prices + normalized_volumes
        
        return np.array(feature_vector, dtype=np.float32).reshape(1, -1)
    
    async def predict(self, klines: list[Kline], window_size: int = 60) -> Dict[str, Any]:
        """
        Predict future price movement (async wrapper for thread pool execution).
        
        Args:
            klines: Historical kline data
            window_size: Number of candles to use as input
        
        Returns:
            Dict with prediction, confidence, and direction
        
        Example:
            >>> prediction = await predictor.predict(klines)
            >>> print(f"Direction: {prediction['direction']}, Confidence: {prediction['confidence']}")
        """
        import asyncio
        
        # Run synchronous inference in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._predict_sync, klines, window_size)
    
    def _predict_sync(self, klines: list[Kline], window_size: int = 60) -> Dict[str, Any]:
        """
        Synchronous prediction method (runs in thread pool).
        
        Args:
            klines: Historical kline data
            window_size: Number of candles to use as input
        
        Returns:
            Dict with prediction, confidence, and direction
        """
        try:
            if self.interpreter is None:
                # Dummy prediction based on recent trend
                return self._dummy_predict(klines)
            
            # Prepare features
            features = self.prepare_features(klines, window_size)
            
            # Get input/output shapes
            input_shape = self.input_details[0]['shape']
            
            # Reshape if needed
            if features.shape != tuple(input_shape):
                # Try to adapt features to model input shape
                if features.shape[1] > input_shape[1]:
                    features = features[:, :input_shape[1]]
                elif features.shape[1] < input_shape[1]:
                    # Pad with zeros
                    padding = np.zeros((1, input_shape[1] - features.shape[1]))
                    features = np.concatenate([features, padding], axis=1)
            
            # Set input tensor
            self.interpreter.set_tensor(self.input_details[0]['index'], features)
            
            # Run inference
            self.interpreter.invoke()
            
            # Get output
            output = self.interpreter.get_tensor(self.output_details[0]['index'])
            
            # Interpret output (assuming binary classification: up/down)
            if output.shape[-1] >= 2:
                up_prob = float(output[0][1])
                down_prob = float(output[0][0])
                direction = 'UP' if up_prob > down_prob else 'DOWN'
                confidence = abs(up_prob - down_prob)
            else:
                # Regression output
                price_change = float(output[0][0])
                direction = 'UP' if price_change > 0 else 'DOWN'
                confidence = min(abs(price_change) / 10.0, 1.0)
            
            return {
                'direction': direction,
                'confidence': confidence,
                'prediction': output.tolist(),
                'current_price': klines[-1].close_price if klines else 0.0
            }
        except Exception as e:
            self.logger.error(f"Error in prediction: {e}")
            return self._dummy_predict(klines)
    
    def _dummy_predict(self, klines: list[Kline]) -> Dict[str, Any]:
        """Dummy prediction based on simple trend analysis."""
        if len(klines) < 5:
            return {
                'direction': 'NEUTRAL',
                'confidence': 0.5,
                'prediction': None,
                'current_price': klines[-1].close_price if klines else 0.0
            }
        
        # Simple trend-based prediction
        recent_prices = [k.close_price for k in klines[-5:]]
        price_change = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
        
        if abs(price_change) < 0.001:  # Less than 0.1% change
            direction = 'NEUTRAL'
            confidence = 0.3
        elif price_change > 0:
            direction = 'UP'
            confidence = min(0.7, 0.5 + abs(price_change) * 10)
        else:
            direction = 'DOWN'
            confidence = min(0.7, 0.5 + abs(price_change) * 10)
        
        return {
            'direction': direction,
            'confidence': confidence,
            'prediction': None,
            'current_price': klines[-1].close_price if klines else 0.0
        }
