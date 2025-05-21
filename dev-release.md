# Dev Release Guide

1. Edit `setup.py`  
   - Bump version: `version="0.x.y"`

2. Clean old builds

   - **Windows (Command Prompt):**
      ```cmd
      rmdir /s /q dist
      ```

   - **Windows (PowerShell):**
      ```powershell
      Remove-Item -Recurse -Force dist
      ```

   - **Linux/macOS:**
      ```sh
      rm -rf dist
      ```

3. Build package
   ```sh
   python -m build
   ```

4. Upload to PyPI
   ```sh
   twine upload dist/*
   ```
