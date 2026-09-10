import json,sys
from pathlib import Path
status="PASS"
try:
    from subject import validate_findings
    if sys.argv[1] == "normal":
        assert validate_findings(json.loads(Path("findings.json").read_text()))
    else:
        try: validate_findings({"findings":[{"claim":"unsupported","sources":[]}]})
        except ValueError: pass
        else: raise AssertionError("missing source accepted")
except Exception as exc:
    status="FAIL"
    print(str(exc))
Path(sys.argv[2]).write_text(json.dumps({"tests":[{"id":sys.argv[1],"status":status}]}))
sys.exit(0 if status=="PASS" else 1)
