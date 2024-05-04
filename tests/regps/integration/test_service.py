import falcon
from falcon.testing import create_environ
from regps.app import service
from regps.app import tasks
from keri.core import coring

import pytest

# @pytest.fixture(autouse=True)
# def setup():
#     # Your setup code goes here
#     print("Setting up")


#currently needs a pre-loaded vlei-verifier populated per signify-ts vlei-verifier test
def test_verify_cig():
    # AID and SAID should be the same as what is in credential.cesr for the ECR credential
    # see https://trustoverip.github.io/tswg-acdc-specification/#top-level-fields to understand the fields/values
    AID = "EP4kdoVrDh4Mpzh2QbocUYIv4IjLZLDU367UO0b40f6x"
    SAID = "EElnd1DKvcDzzh7u7jBjsg2X9WgdQQuhgiu80i2VR-gk"

    # '"@method": null\n"@path": /request/verify/EP4kdoVrDh4Mpzh2QbocUYIv4IjLZLDU367UO0b40f6x\n"signify-resource": EP4kdoVrDh4Mpzh2QbocUYIv4IjLZLDU367UO0b40f6x\n"signify-timestamp": 2024-05-03T19:21:16.745000+00:00\n"@signature-params: (@method @path signify-resource signify-timestamp);created=1714764449;keyid=BPoZo2b3r--lPBpURvEDyjyDkS65xBEpmpQhHQvrwlBE;alg=ed25519"'

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
    result = client.simulate_get(f"/verify/header", headers=headers)
    assert result.status == falcon.HTTP_401 # this signature is for a direct call to the verification service instead of /verify/header from the server call.
    # assert result.aid == AID
    # assert (
    #     result.cig.qb64
    #     == "0BAFWzKD9FsC5aq7ACgBsseYZBtWffuzgQGP72o1v0_PEpJRNzjmgVcANyBLdtq3W2IX-ZEDWFwikMD156pxEvsA"
    # )
    # assert (
    #     result.ser
    #     == '"@method": POST\n"@path": /\n"signify-resource": EP4kdoVrDh4Mpzh2QbocUYIv4IjLZLDU367UO0b40f6x\n"signify-timestamp": 2024-05-04T14:47:24.307000+00:00\n"@signature-params: (@method @path signify-resource signify-timestamp);created=1714834044;keyid=BPoZo2b3r--lPBpURvEDyjyDkS65xBEpmpQhHQvrwlBE;alg=ed25519"'
    # )


#     hby.kevers[hab.pre] = hab.kever

#     auth = Authorizer(hby, vdb, eccrdntler.rgy.reger, [LEI1])
#     auth.processPresentations()

#     result = client.simulate_get(f'/authorizations/{hab.pre}')
#     assert result.status == falcon.HTTP_OK

#     data = 'this is the raw data'
#     raw = data.encode("utf-8")
#     cig = hab.sign(ser=raw, indexed=False)[0]
#     assert cig.qb64 == '0BChOKVR4b5t6-cXKa3u3hpl60X1HKlSw4z1Rjjh1Q56K1WxYX9SMPqjn-rhC4VYhUcIebs3yqFv_uu0Ou2JslQL'
#     assert hby.kevers[hab.pre].verfers[0].verify(sig=cig.raw, ser=raw)
#     result = client.simulate_post(f'/request/verify/{hab.pre}',params={'data': data, 'sig': cig.qb64})
#     assert result.status == falcon.HTTP_202

#     data = '"@method": GET\n"@path": /verify/header\n"signify-resource": EHYfRWfM6RxYbzyodJ6SwYytlmCCW2gw5V-FsoX5BgGx\n"signify-timestamp": 2024-05-01T19:54:53.571000+00:00\n"@signature-params: (@method @path signify-resource signify-timestamp);created=1714593293;keyid=BOieebDzg4uaqZ2zuRAX1sTiCrD3pgGT3HtxqSEAo05b;alg=ed25519"'
#     raw = data.encode("utf-8")
#     cig = hab.sign(ser=raw, indexed=False)[0]
#     assert cig.qb64 == '0BB1Z2DS3QvIBdZJ1Q7yuZCUG-6YkVXDm7dcGbIFEIsLYEBfFXk8P_Y9FUACTlv5vCHeCet70QzVdR8fu5tLBKkP'
#     assert hby.kevers[hab.pre].verfers[0].verify(sig=cig.raw, ser=raw)
