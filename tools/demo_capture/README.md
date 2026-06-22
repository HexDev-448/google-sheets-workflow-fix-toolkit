# Demo Capture

Use this optional script after the Streamlit app is running.

```powershell
python -m pip install -r requirements-dev.txt
python tools/demo_capture/capture_web_demo.py
```

If Playwright reports a missing browser:

```powershell
python -m playwright install chromium
python tools/demo_capture/capture_web_demo.py
```

Default target:

```text
http://localhost:8501
```

Default output:

```text
screenshots/workflow-preview.png
```

The script uses Playwright if it is installed in your environment. It does not upload screenshots or connect to Google services.
