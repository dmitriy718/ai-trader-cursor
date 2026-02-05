"""Create a dummy TensorFlow Lite model for demonstration."""

import tensorflow as tf
import numpy as np
from pathlib import Path


def create_dummy_model(output_path: str):
    """
    Create a simple dummy TensorFlow Lite model.
    
    This is a placeholder model. In production, you would train
    a real model on historical price data.
    """
    # Create a simple sequential model
    model = tf.keras.Sequential([
        tf.keras.layers.Dense(64, activation='relu', input_shape=(120,)),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(32, activation='relu'),
        tf.keras.layers.Dense(2, activation='softmax')  # Binary classification: up/down
    ])
    
    # Compile model
    model.compile(
        optimizer='adam',
        loss='categorical_crossentropy',
        metrics=['accuracy']
    )
    
    # Train on dummy data (just to create a valid model)
    dummy_x = np.random.random((100, 120))
    dummy_y = np.random.randint(2, size=(100, 2))
    model.fit(dummy_x, dummy_y, epochs=1, verbose=0)
    
    # Convert to TensorFlow Lite
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    tflite_model = converter.convert()
    
    # Save model
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'wb') as f:
        f.write(tflite_model)
    
    print(f"Dummy model created at: {output_path}")
    print(f"Model size: {len(tflite_model) / 1024:.2f} KB")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Create dummy TensorFlow Lite model")
    parser.add_argument(
        "--output",
        type=str,
        default="models/price_predictor.tflite",
        help="Output path for the model"
    )
    args = parser.parse_args()
    
    create_dummy_model(args.output)
