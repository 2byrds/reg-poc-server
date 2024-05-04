import falcon
import os
import requests
from time import sleep

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
    gres = requests.get(f"{auths_url}{aid}", headers={"Content-Type": "application/json"})
    print(f"login status: {gres}")
    return gres

def verify_vlei(aid: str, said: str, vlei: str) -> dict:
    # first check to see if we're already logged in
    print(f"Login verification started {aid} {said} {vlei[:50]}")

    login_response = check_login(aid)
    print(f"Login check {login_response.status_code} {login_response.text[:500]}")

    if str(login_response.status_code) == str(falcon.http_status_to_code(falcon.HTTP_OK)):
        print("already logged in")
        return login_response
    else:
        print(f"putting to {presentations_url}{said}")
        presentation_response = requests.put(f"{presentations_url}{said}", headers={"Content-Type": "application/json+cesr"}, data=vlei)
        print(f"put response {presentation_response.text}")

        if presentation_response.status_code == falcon.http_status_to_code(falcon.HTTP_ACCEPTED):
            login_response = None
            while(login_response == None or login_response.status_code == falcon.http_status_to_code(falcon.HTTP_404)):
                login_response = check_login(aid)
                print(f"polling result {login_response}")
                sleep (1)
            return login_response
        else:
            return presentation_response
        
def verify_cig(aid,cig,ser) -> falcon.Response:
    print("Verify header sig started aid = {}, cig = {}, ser = {}....".format(aid,cig,ser))
    print("posting to {}".format(request_url+f"{aid}"))
    pres = requests.post(request_url+aid, params={"sig": cig,"data": ser})
    print("Verify header sig response {}".format(pres.text))
    return pres
        
def check_upload(aid: str, dig: str) -> dict:
    return _upload(aid, dig)

def _upload(aid: str, dig: str) -> falcon.Response:
    print(f"checking upload: aid {aid} and dig {dig}")
    print(f"getting from {reports_url}{aid}/{dig}")
    reports_response = requests.get(f"{reports_url}{aid}/{dig}", headers={"Content-Type": "application/json"})
    print(f"upload status: {reports_response}")
    return reports_response

def upload(aid: str, dig: str, contype: str, report) -> dict:
    print(f"report type {type(report)}")
    # first check to see if we've already uploaded
    upload_response = _upload(aid, dig)
    if upload_response.status_code == falcon.http_status_to_code(falcon.HTTP_ACCEPTED):
        print("already uploaded")
        return upload_response
    else:
        print(f"posting to {reports_url}{aid}/{dig}")
        presentation_response = requests.post(f"{reports_url}{aid}/{dig}", headers={"Content-Type": contype}, data=report)
        print(f"post response {presentation_response.text}")

        if presentation_response.status_code == falcon.http_status_to_code(falcon.HTTP_ACCEPTED):
            upload_response = None
            while(upload_response == None or upload_response.status_code == falcon.http_status_to_code(falcon.HTTP_404)):
                upload_response = _upload(aid,dig)
                print(f"polling result {upload_response.text}")
                sleep (1)
            return upload_response
        else:
            return presentation_response