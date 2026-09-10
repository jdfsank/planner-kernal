import json,sys
from pathlib import Path
status="PASS"
try:
    from subject import slug
    if sys.argv[1] == "normal":
        assert slug("  Hello   WORLD ") == "hello-world"
    else:
        try: slug("")
        except ValueError: pass
        else: raise AssertionError("empty text accepted")
except Exception as exc:
    status="FAIL"
    print(str(exc))
Path(sys.argv[2]).write_text(json.dumps({"tests":[{"id":sys.argv[1],"status":status}]}))
sys.exit(0 if status=="PASS" else 1)
