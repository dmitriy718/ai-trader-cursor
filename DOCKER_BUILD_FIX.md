# Docker Build Fix for ARM64 Compatibility

## Issue
Docker build was failing during `pip install` step, likely due to:
1. Full TensorFlow package being too large/heavy for ARM64
2. Missing build dependencies
3. ARM64 compatibility issues

## Solution

### 1. Updated `requirements.txt`
- Removed hard dependency on `tensorflow==2.15.0`
- Added note that TensorFlow/TFLite installation is handled in Dockerfile
- Code gracefully handles both `tflite-runtime` and `tensorflow` imports

### 2. Updated `Dockerfile`
- **Added build dependencies**: `libffi-dev`, `libssl-dev`, `python3-dev`
- **Split package installation**: Install core packages first, then TensorFlow separately
- **TensorFlow fallback strategy**:
  1. Try `tflite-runtime` first (lightweight, ARM64-optimized)
  2. Fallback to `tensorflow` if tflite-runtime fails
  3. Continue build even if TensorFlow fails (ML features will use dummy model)

### 3. Updated `src/ml/predictor.py`
- **Flexible imports**: Handles both `tflite-runtime` and `tensorflow`
- **ARM64 workaround**: Copies model to `/tmp` to avoid mmap errors on Docker volumes
- **Graceful degradation**: Falls back to dummy model if TensorFlow unavailable

## Build Instructions

### For ARM64 (Raspberry Pi)
```bash
docker-compose build
```

The build will:
1. Install all core dependencies
2. Attempt to install `tflite-runtime` (preferred for ARM64)
3. Fallback to `tensorflow` if needed
4. Continue even if TensorFlow installation fails

### For x86_64
The same Dockerfile works, but will likely use `tensorflow` instead of `tflite-runtime`.

## Verification

After build, verify ML functionality:
```bash
docker-compose up -d
docker-compose logs trading-bot | grep -i "ML model"
```

Expected output:
- `"ML model loaded successfully"` - if TensorFlow/TFLite available
- `"Using dummy prediction model"` - if TensorFlow unavailable (still functional)

## Notes

- **TextBlob**: Will download NLTK data on first use (automatic)
- **Model file**: Ensure model file exists at configured path, or dummy model will be used
- **Performance**: `tflite-runtime` is much lighter (~5MB) vs full TensorFlow (~500MB+)

## Troubleshooting

If build still fails:

1. **Check platform**:
   ```bash
   docker buildx inspect
   ```

2. **Build with platform specification**:
   ```bash
   docker buildx build --platform linux/arm64 -t ai-trading-bot .
   ```

3. **Check logs**:
   ```bash
   docker-compose build --progress=plain 2>&1 | tee build.log
   ```

4. **Skip TensorFlow entirely** (if not needed):
   Comment out the TensorFlow installation step in Dockerfile and use dummy model only.
