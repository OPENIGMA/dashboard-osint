#!/usr/bin/env python3
import sys, json, os, datetime

def check_file(path):
    if not os.path.exists(path):
        print(f"ERROR: {path} not found")
        return False
    try:
        with open(path, 'r', encoding='utf-8') as f:
            json.load(f)
    except Exception as e:
        print(f"ERROR: {path} not valid JSON: {e}")
        return False
    print(f"OK: {path} parsed")
    return True

ok = True
ok &= check_file('data_feed.json')
ok &= check_file('trending.json')

if not ok:
    sys.exit(2)

for p in ('data_feed.json','trending.json'):
    try:
        mtime = os.path.getmtime(p)
        age_hours = (datetime.datetime.now().timestamp() - mtime) / 3600
        print(f"{p} age: {age_hours:.1f}h")
    except Exception:
        pass

sys.exit(0)
