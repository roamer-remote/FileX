# OCR golden fixtures (103 P2)

Each `*.png` pairs with `*.expected.txt` (reference transcript).

```bash
python scripts/kb_ocr_eval.py --fixture backend/tests/fixtures/ocr_golden/
```

Not required on default PR CI; run locally or optional pipeline job after kb-extract rebuild.
