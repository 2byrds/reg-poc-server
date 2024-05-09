import falcon
import json
import os
import requests

auths_url = "http://127.0.0.1:7676/authorizations/"
presentations_url = "http://127.0.0.1:7676/presentations/"
reports_url = "http://127.0.0.1:7676/reports/"
request_url = "http://localhost:7676/request/verify/"

VERIFIER_AUTHORIZATIONS = os.environ.get('VERIFIER_AUTHORIZATIONS')
if VERIFIER_AUTHORIZATIONS is None:
        print(f"VERIFIER_AUTHORIZATIONS is not set. Using default {auths_url}")
else:
        print(f"VERIFIER_AUTHORIZATIONS is set. Using {VERIFIER_AUTHORIZATIONS}")
        auths_url = VERIFIER_AUTHORIZATIONS
        
VERIFIER_PRESENTATIONS = os.environ.get('VERIFIER_PRESENTATIONS')
if VERIFIER_PRESENTATIONS is None:
        print(f"VERIFIER_PRESENTATIONS is not set. Using default {presentations_url}")
else:
        print(f"VERIFIER_PRESENTATIONS is set. Using {VERIFIER_PRESENTATIONS}")
        presentations_url = VERIFIER_PRESENTATIONS

VERIFIER_REPORTS = os.environ.get('VERIFIER_REPORTS')
if VERIFIER_REPORTS is None:
        print(f"VERIFIER_REPORTS is not set. Using default {reports_url}")
else:
        print(f"VERIFIER_REPORTS is set. Using {VERIFIER_REPORTS}")
        reports_url = VERIFIER_REPORTS
        
VERIFIER_REQUESTS = os.environ.get('VERIFIER_REQUESTS')
if VERIFIER_REQUESTS is None:
        print(f"VERIFIER_REQUESTS is not set. Using default {request_url}")
else:
        print(f"VERIFIER_REQUESTS is set. Using {VERIFIER_REQUESTS}")
        request_url = VERIFIER_REQUESTS

def check_login(aid: str) -> falcon.Response:
    print(f"checking login: {aid}")
    print(f"getting from {auths_url}{aid}")
    res = requests.get(f"{auths_url}{aid}", headers={"Content-Type": "application/json"})
    print(f"login status: {json.dumps(res.json())}")
    return res

def verify_vlei(said: str, vlei: str) -> falcon.Response:
    print(f"Verify vlei task started {said} {vlei[:50]}")
    print(f"presenting vlei ecr to url {presentations_url}{said}")
    res = requests.put(f"{presentations_url}{said}", headers={"Content-Type": "application/json+cesr"}, data=vlei)
    print(f"verify vlei task response {json.dumps(res.json())}")
    return res
        
def verify_cig(aid,cig,ser) -> falcon.Response:
    print("Verify header sig started aid = {}, cig = {}, ser = {}....".format(aid,cig,ser))
    print("posting to {}".format(request_url+f"{aid}"))
    res = requests.post(request_url+aid, params={"sig": cig,"data": ser})
    print(f"Verify sig response {json.dumps(res.json())}")
    return res

def check_upload(aid: str, dig: str) -> falcon.Response:
    print(f"checking upload: aid {aid} and dig {dig}")
    print(f"getting from {reports_url}{aid}/{dig}")
    res = requests.get(f"{reports_url}{aid}/{dig}", headers={"Content-Type": "application/json"})
    print(f"upload status: {json.dumps(res.json())}")
    return res

def upload(aid: str, dig: str, contype: str, report) -> falcon.Response:
    print(f"upload report type {type(report)}")
    # first check to see if we've already uploaded
    res = check_upload(aid, dig)
    if res.status_code == falcon.http_status_to_code(falcon.HTTP_ACCEPTED):
        print(f"upload already uploaded: {json.dumps(res.json())}")
    else:
        print(f"upload posting to {reports_url}{aid}/{dig}")
        res = requests.post(f"{reports_url}{aid}/{dig}", headers={"Content-Type": contype}, data=report)
        print(f"post response {json.dumps(res.json())}")
    return res