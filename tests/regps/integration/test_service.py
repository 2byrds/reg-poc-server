import falcon
from falcon.testing import create_environ
import os
from regps.app import service
import pytest
import subprocess
import time

# @pytest.fixture(autouse=True)
# def setup():
#     # Your setup code goes here
#     print("Setting up")

@pytest.fixture(scope='session')
def start_gunicorn():
    # Start Gunicorn server
    server = subprocess.Popen(['gunicorn', 'regps.app.service:app', '-b', '0.0.0.0:8000'])
    # Give it some time to start up
    while True:
        time.sleep(3)
    yield
    # Stop Gunicorn server after tests have finished
    server.terminate()
    
# def test_local(start_gunicorn):
#     print("Running test_local so that you can debug the server")

#currently needs a pre-loaded vlei-verifier populated per signify-ts vlei-verifier test
def test_ends():
    # AID and SAID should be the same as what is in credential.cesr for the ECR credential
    # see https://trustoverip.github.io/tswg-acdc-specification/#top-level-fields to understand the fields/values
    AID = "EP4kdoVrDh4Mpzh2QbocUYIv4IjLZLDU367UO0b40f6x"
    SAID = "EElnd1DKvcDzzh7u7jBjsg2X9WgdQQuhgiu80i2VR-gk"

    # got these from signify-ts integration test
    headers = {
        "HOST": "localhost:7676",
        "CONNECTION": "keep-alive",
        "METHOD": "POST",
        "SIGNATURE": 'indexed="?0";signify="0BBbeeBw3lVmQWYBpcFH9KmRXZocrqLH_LZL4aqg5W9-NMdXqIYJ-Sao7colSTJOuYllMXFfggoMhkfpTKnvPhUF"',
        "SIGNATURE-INPUT": 'signify=("@method" "@path" "signify-resource" "signify-timestamp");created=1714854033;keyid="BPoZo2b3r--lPBpURvEDyjyDkS65xBEpmpQhHQvrwlBE";alg="ed25519"',
        "SIGNIFY-RESOURCE": "EP4kdoVrDh4Mpzh2QbocUYIv4IjLZLDU367UO0b40f6x",
        "SIGNIFY-TIMESTAMP": "2024-05-04T20:20:33.730000+00:00",
        "ACCEPT": "*/*",
        "ACCEPT-LANGUAGE": "*",
        "SEC-FETCH-MODE": "cors",
        "USER-AGENT": "node",
        "ACCEPT-ENCODING": "gzip, deflate",
    }

    app = service.falcon_app()
    client = falcon.testing.TestClient(app)
    
    result = client.simulate_get(f"/ping", headers=headers)
    assert result.status == falcon.HTTP_200
    assert result.text == "Pong"
    
    result = client.simulate_get(f"/checklogin/{AID}", headers=headers)
    assert result.status == falcon.HTTP_401
    
    with open(f"./data/credential.cesr", 'r') as cfile:
        vlei_ecr = cfile.read()
        headers['Content-Type'] = 'application/json+cesr'
        result = client.simulate_post(f"/login", json={"said": SAID, "vlei": vlei_ecr}, headers=headers)
        assert result.status == falcon.HTTP_202
    
    result = client.simulate_get(f"/checklogin/{AID}", headers=headers)
    assert result.status == falcon.HTTP_200
    
    result = client.simulate_get(f"/login", headers=headers)
    assert result.status == falcon.HTTP_401 # fail because this signature is for a direct call to the verification service instead of /verify/header from the server call.