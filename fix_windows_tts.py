from pathlib import Path

path = Path("final.py")
text = path.read_text(encoding="utf-8")

text = text.replace("import shutil\nimport tempfile\nimport time\n", "import shutil\nimport subprocess\nimport tempfile\n")
text = text.replace("import pyttsx3\n", "")

old_list = '''def list_voices() -> list[tuple[str, str]]:\n    engine = pyttsx3.init()\n    voices = engine.getProperty("voices")\n    result = []\n    for voice in voices:\n        name = getattr(voice, "name", "System voice")\n        result.append((name, voice.id))\n    engine.stop()\n    return result\n'''

new_list = '''def _run_powershell(script: str) -> str:\n    completed = subprocess.run(\n        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],\n        check=True,\n        capture_output=True,\n        text=True,\n        encoding="utf-8",\n        errors="replace",\n    )\n    return completed.stdout.strip()\n\n\ndef list_voices() -> list[tuple[str, str]]:\n    script = (\n        "Add-Type -AssemblyName System.Speech; "\n        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "\n        "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }; "\n        "$s.Dispose()"\n    )\n    names = [line.strip() for line in _run_powershell(script).splitlines() if line.strip()]\n    return [(name, name) for name in names]\n'''

old_narration = '''def create_narration(text: str, output_path: Path, voice_id: str, rate: int) -> None:\n    engine = pyttsx3.init()\n    engine.setProperty("voice", voice_id)\n    engine.setProperty("rate", rate)\n    engine.save_to_file(text, str(output_path))\n    engine.runAndWait()\n    engine.stop()\n\n    for _ in range(30):\n        if output_path.exists() and output_path.stat().st_size > 0:\n            return\n        time.sleep(0.2)\n    raise RuntimeError("Windows narration did not create an audio file.")\n'''

new_narration = '''def create_narration(text: str, output_path: Path, voice_id: str, rate: int) -> None:\n    safe_text = text.replace("'", "''").replace("`", "``")\n    safe_voice = voice_id.replace("'", "''")\n    safe_path = str(output_path.resolve()).replace("'", "''")\n    sapi_rate = max(-10, min(10, round((rate - 170) / 5)))\n\n    script = (\n        "Add-Type -AssemblyName System.Speech; "\n        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "\n        f"$s.SelectVoice('{safe_voice}'); "\n        f"$s.Rate = {sapi_rate}; "\n        f"$s.SetOutputToWaveFile('{safe_path}'); "\n        f"$s.Speak('{safe_text}'); "\n        "$s.SetOutputToNull(); $s.Dispose()"\n    )\n    _run_powershell(script)\n\n    if not output_path.exists() or output_path.stat().st_size < 1000:\n        raise RuntimeError("Windows narration did not create a valid WAV file.")\n'''

if old_list not in text or old_narration not in text:
    raise SystemExit("Could not locate the original narration functions. Pull the latest local-offline-mvp branch first.")

text = text.replace(old_list, new_list).replace(old_narration, new_narration)
path.write_text(text, encoding="utf-8")
print("Windows narration patch applied to final.py")
