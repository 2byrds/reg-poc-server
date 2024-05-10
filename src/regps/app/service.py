import time
from .tasks import check_login, check_upload, upload, verify_vlei, verify_cig
import falcon
from falcon import media
from falcon.http_status import HTTPStatus
import json
from keri.end import ending
import os
from swagger_ui import api_doc

ROUTE_PING = "/ping"
ROUTE_LOGIN = "/login"
ROUTE_CHECK_LOGIN = "/checklogin"
ROUTE_UPLOAD = "/upload"
ROUTE_CHECK_UPLOAD = "/checkupload"
ROUTE_STATUS = "/status"

uploadStatus = {}

def copyResponse(actual: falcon.Response, copyme: falcon.Response):
    actual.status = str(copyme.status_code) + " " + copyme.reason
    actual.data = json.dumps(copyme.json()).encode("utf-8")
    actual.content_type = copyme.headers["Content-Type"]

def initStatusDb(aid):
    if aid not in uploadStatus:
        print("Initialized status db for {}".format(aid))
        uploadStatus[aid] = []
    else:
        print("Status db already initialized for {}".format(aid))
    return


# the signature is a keri cigar objects
class VerifySignedHeaders:

    DefaultFields = ["Signify-Resource", "@method", "@path", "Signify-Timestamp"]

    def process_request(self, req: falcon.Request, resp: falcon.Response):
        print(f"Processing signed header verification request {req}")
        aid, cig, ser = self.handle_headers(req)
        res = verify_cig(aid, cig, ser)
        print(f"VerifySignedHeaders.on_post: response {res}")

        if res.status_code <= 400:
            initStatusDb(aid)
        return res

    def handle_headers(self, req):
        print(f"processing header req {req}")

        headers = req.headers
        if "SIGNATURE-INPUT" not in headers or "SIGNATURE" not in headers or "SIGNIFY-RESOURCE" not in headers or "SIGNIFY-TIMESTAMP" not in headers:
            return False

        siginput = headers["SIGNATURE-INPUT"]
        if not siginput:
            return False
        signature = headers["SIGNATURE"]
        if not signature:
            return False
        resource = headers["SIGNIFY-RESOURCE"]
        if not resource:
            return False
        timestamp = headers["SIGNIFY-TIMESTAMP"]
        if not timestamp:
            return False

        inputs = ending.desiginput(siginput.encode("utf-8"))
        inputs = [i for i in inputs if i.name == "signify"]

        if not inputs:
            return False

        for inputage in inputs:
            items = []
            for field in inputage.fields:
                if field.startswith("@"):
                    if field == "@method":
                        items.append(f'"{field}": {req.method}')
                    elif field == "@path":
                        items.append(f'"{field}": {req.path}')

                else:
                    key = field.upper()
                    field = field.lower()
                    if key not in headers:
                        continue

                    value = ending.normalize(headers[key])
                    items.append(f'"{field}": {value}')

            values = [f"({' '.join(inputage.fields)})", f"created={inputage.created}"]
            if inputage.expires is not None:
                values.append(f"expires={inputage.expires}")
            if inputage.nonce is not None:
                values.append(f"nonce={inputage.nonce}")
            if inputage.keyid is not None:
                values.append(f"keyid={inputage.keyid}")
            if inputage.context is not None:
                values.append(f"context={inputage.context}")
            if inputage.alg is not None:
                values.append(f"alg={inputage.alg}")

            params = ";".join(values)

            items.append(f'"@signature-params: {params}"')
            ser = "\n".join(items)

            signages = ending.designature(signature)
            cig = signages[0].markers[inputage.name]
            assert len(signages) == 1
            assert signages[0].indexed is False
            assert "signify" in signages[0].markers

            aid = resource
            sig = cig.qb64
            print(f"verification input aid={aid} ser={ser} cig={sig}")
            return aid, sig, ser


class LoginTask:

    # Expects a JSON object with the following fields:
    # - said: the SAID of the credential
    # - vlei: the vLEI ECR CESR
    def on_post(self, req: falcon.Request, resp: falcon.Response):
        print("LoginTask.on_post")
        try:
            if req.content_type not in ("application/json",):
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.data = json.dumps(
                    dict(msg=f"invalid content type={req.content_type} for VC presentation, should be application/json",
                        exception_type=type(e).__name__,
                        exception_message=str(e)
                    )).encode("utf-8")
                return

            data = req.media
            if data.get("said") is None:
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.data = json.dumps(
                dict(msg=f"requests with a said is required",
                    exception_type=type(e).__name__,
                    exception_message=str(e)
                )).encode("utf-8")
                return
            if data.get("vlei") is None:
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.data = json.dumps(
                dict(msg=f"requests with vlei ecr cesr is required",
                    exception_type=type(e).__name__,
                    exception_message=str(e)
                )).encode("utf-8")
                return

            print(f"LoginTask.on_post: sending login cred {str(data)[:50]}...")

            copyResponse(resp, verify_vlei(data["said"], data["vlei"]))

            print(f"LoginTask.on_post: received data {resp.status}")
            return
        except Exception as e:
            print(f"LoginTask.on_post: Exception: {e}")
            resp.status = falcon.HTTP_500
            resp.data = json.dumps(
                dict(msg="Login request failed",
                    exception_type=type(e).__name__,
                    exception_message=str(e)
                )).encode("utf-8")
            return

    def on_get(self, req: falcon.Request, resp: falcon.Response, aid):
        print("LoginTask.on_get")
        try:
            print(f"LoginTask.on_get: sending aid {aid}")
            copyResponse(resp, check_login(aid))
            print(f"LoginTask.on_get: response {json.dumps(resp.data.decode('utf-8'))}")
            return
        except Exception as e:
            print(f"LoginTask.on_get: Exception: {e}")
            resp.status = falcon.HTTP_500
            resp.data = json.dumps(
                dict(msg="Login check request failed",
                    exception_type=type(e).__name__,
                    exception_message=str(e)
                )).encode("utf-8")
            return


class UploadTask:

    def __init__(self, verCig: VerifySignedHeaders) -> None:
        self.verCig = verCig

    def on_post(self, req: falcon.Request, resp: falcon.Response, aid, dig):
        print("UploadTask.on_post {}".format(req))
        try :
            check_headers = self.verCig.process_request(req, resp)
            if check_headers.status_code >= 400:
                print(f"UploadTask.on_post: Invalid signature on headers or error was received")
                return copyResponse(resp,check_headers)

            raw = req.bounded_stream.read()
            print(
                f"UploadTask.on_post: request for {aid} {dig} {raw} {req.content_type}"
            )
            upload_resp = upload(aid, dig, req.content_type, raw)
            if upload_resp.status_code >= 400:
                print(f"UploadTask.on_post: Invalid signature on report or error was received")
                return copyResponse(resp,upload_resp)
            else:
                print(f"UploadTask.on_post: completed upload for {aid} {dig} with code {upload_resp.status_code}")
                uploadStatus[f"{aid}"].append(json.dumps(upload_resp.json()))
                return copyResponse(resp,upload_resp)
            
        except Exception as e:
            print(f"Upload.on_post: Exception: {e}")
            resp.status = falcon.HTTP_500
            resp.data = json.dumps(
                dict(msg="Upload request failed",
                    exception_type=type(e).__name__,
                    exception_message=str(e)
                )).encode("utf-8")
            return

    def on_get(self, req: falcon.Request, resp: falcon.Response, aid, dig):
        print("UploadTask.on_get")
        copyResponse(resp, self.verCig.process_request(req, resp))
        if resp:
            print(f"UploadTask.on_post: Invalid signature on headers")
            return resp
        try:
            print(f"UploadTask.on_get: sending aid {aid} for dig {dig}")
            copyResponse(resp, check_upload(aid, dig))
            print(f"UploadTask.on_get: received data {json.dumps(resp.data)}")
            return
        except Exception as e:
            print(f"UploadTask.on_get: Exception: {e}")
            resp.status = falcon.HTTP_500
            resp.data = json.dumps(
                dict(msg="Login check request failed",
                    exception_type=type(e).__name__,
                    exception_message=str(e)
                )).encode("utf-8")
            return

class StatusTask:

    def __init__(self, verCig: VerifySignedHeaders) -> None:
        self.verCig = verCig

    def on_get(self, req: falcon.Request, resp: falcon.Response, aid):
        print(f"StatusTask.on_get request {req}")
        try :
            check_headers = self.verCig.process_request(req, resp)
            if check_headers.status_code >= 400:
                print(f"StatusTask.on_get: Invalid signature on headers or error was received")
                return copyResponse(resp,check_headers)
            
            print(f"StatusTask.on_get: aid {aid}")
            if aid not in uploadStatus:
                print(f"StatusTask.on_post: Cannot find status for {aid}")
                resp.data = json.dumps(dict(msg=f"AID not logged in: {aid}")).encode("utf-8")
                resp.status = falcon.HTTP_401
                return resp
            else:
                responses = uploadStatus[f"{aid}"]
                if len(responses) == 0:
                    print(f"StatusTask.on_get: Empty upload status list for aid {aid}")
                    resp.status = falcon.HTTP_200
                    resp.data = json.dumps(dict(msg="No uploads found")).encode("utf-8")
                    return resp
                else:
                    print(f"StatusTask.on_get: received data {json.dumps(resp.data)}")
                    resp.status = falcon.HTTP_200
                    resp.data = json.dumps(responses).encode("utf-8")
                    return resp
        except Exception as e:
            print(f"Status.on_get: Exception: {e}")
            resp.status = falcon.HTTP_500
            resp.data = json.dumps(
                dict(msg="Status request failed",
                    exception_type=type(e).__name__,
                    exception_message=str(e)
                )).encode("utf-8")
            return resp


class HandleCORS(object):
    def process_request(self, req: falcon.Request, resp: falcon.Response):
        resp.set_header("Access-Control-Allow-Origin", "*")
        resp.set_header("Access-Control-Allow-Methods", "*")
        resp.set_header("Access-Control-Allow-Headers", "*")
        resp.set_header("Access-Control-Max-Age", 1728000)  # 20 days
        if req.method == "OPTIONS":
            raise HTTPStatus(falcon.HTTP_200, text="\n")
            return


class PingResource:
    def on_get(self, req: falcon.Request, resp: falcon.Response):
        """Handles GET requests"""
        resp.status = falcon.HTTP_200
        resp.content_type = falcon.MEDIA_TEXT
        resp.text = "Pong"
        return


# class PingSecureResource:

#     def __init__(self, verCig: VerifySignedHeaders) -> None:
#         self.verCig = verCig

#     def on_get(self, req: falcon.Request, resp: falcon.Response, aid):
#         sig_check = self.verCig.process_request(req: falcon.Request, resp: falcon.Response)
#         if sig_check:
#             print(f"SecurePing.on_get: Invalid signature on headers")
#             return sig_check
#         try:
#             print(f"SecurePing.on_get: aid {aid}")
#             """Handles GET requests with headers"""
#             resp.status = falcon.HTTP_200
#             resp.content_type = falcon.MEDIA_TEXT
#             resp.text = "Secure Pong"
#         except Exception as e:
#             print(f"SecurePing.on_get: Exception: {e}")
#             resp.text = f"Exception: {e}"
#             resp.status = falcon.HTTP_500


def getRequiredParam(body, name):
    param = body.get(name)
    if param is None:
        raise falcon.HTTPBadRequest(
            description=f"required field '{name}' missing from request"
        )

    return param


def swagger_ui(app):
    vlei_contents = None
    with open("./data/credential.cesr", "r") as cfile:
        vlei_contents = cfile.read()

    report_zip = None
    with open("./data/report.zip", "rb") as rfile:
        report_zip = rfile

    config = {
        "openapi": "3.0.1",
        "info": {
            "title": "Regulator portal service api",
            "description": "Regulator web portal service api",
            "version": "1.0.0",
        },
        "servers": [{"url": "http://127.0.0.1:8000", "description": "local server"}],
        "tags": [{"name": "default", "description": "default tag"}],
        "paths": {
            "/ping": {
                "get": {
                    "tags": ["default"],
                    "summary": "output pong.",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/text": {
                                    "schema": {"type": "object", "example": "Pong"}
                                }
                            },
                        }
                    },
                }
            },
            "/login": {
                "post": {
                    "tags": ["default"],
                    "summary": "Given an AID and vLEI, returns information about the login",
                    "requestBody": {
                        "required": "true",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "aid": {
                                            "type": "string",
                                            "example": "EHYfRWfM6RxYbzyodJ6SwYytlmCCW2gw5V-FsoX5BgGx",
                                        },
                                        "said": {
                                            "type": "string",
                                            "example": "EH37Qxg6UJF_gboIFAlvqdOu7r6Tz7P7BrVAeyHo_WDL",
                                        },
                                        "vlei": {
                                            "type": "string",
                                            "example": f"{vlei_contents}",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "example": {
                                            "aid": "EHYfRWfM6RxYbzyodJ6SwYytlmCCW2gw5V-FsoX5BgGx",
                                            "said": "EH37Qxg6UJF_gboIFAlvqdOu7r6Tz7P7BrVAeyHo_WDL",
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/checklogin/{aid}": {
                "get": {
                    "tags": ["default"],
                    "summary": "Given an AID returns information about the login",
                    "parameters": [
                        {
                            "in": "path",
                            "name": "aid",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "minimum": 1,
                                "example": "EHYfRWfM6RxYbzyodJ6SwYytlmCCW2gw5V-FsoX5BgGx",
                            },
                            "description": "The AID",
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "example": {
                                            "aid": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk",
                                            "said": "EBdaAMrpqfB0PlTgI3juS8UFgIPAXC1NZd1jSk6acenf",
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/upload/{aid}/{dig}": {
                "post": {
                    "tags": ["default"],
                    "summary": "Given an AID and DIG, returns information about the upload",
                    "parameters": [
                        {
                            "in": "path",
                            "name": "aid",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "minimum": 1,
                                "example": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk",
                            },
                            "description": "The AID",
                        },
                        {
                            "in": "path",
                            "name": "dig",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "minimum": 1,
                                "example": "EC7b6S50sY26HTj6AtQiWMDMucsBxMvThkmrKUBXVMf0",
                            },
                            "description": "The digest of the upload",
                        },
                        {
                            "in": "header",
                            "name": "Signature",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "example": 'indexed="?0";signify="0BCLs_wv3X6YFoFhB7acH_BePXS7zjBJPvuChdr01cM60Igf_sxYsah9sLHP-pMSYFs1Y6zYUo58HVG8tRd4X1IC"',
                            },
                            "description": "The signature of the data",
                        },
                        {
                            "in": "header",
                            "name": "Signature-Input",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "example": 'signify=("@method" "@path" "signify-resource" "signify-timestamp");created=1690462814;keyid="BPmhSfdhCPxr3EqjxzEtF8TVy0YX7ATo0Uc8oo2cnmY9";alg="ed25519"',
                            },
                            "description": "The signature of the data",
                        },
                        {
                            "in": "header",
                            "name": "Signify-Resource",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "example": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk",
                            },
                            "description": "The aid that siged the data",
                        },
                        {
                            "in": "header",
                            "name": "signify-timestamp",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "example": "2023-07-27T13:00:14.802000+00:00",
                            },
                            "description": "The timestamp of the data",
                        },
                    ],
                    "requestBody": {
                        "required": "true",
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "upload": {
                                            "type": "string",
                                            "format": "binary",
                                            "example": f"{report_zip}",
                                        }
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "example": {
                                            "submitter": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk",
                                            "filename": "test_ifgroup2023.zip",
                                            "status": "verified",
                                            "contentType": "application/zip",
                                            "size": 4467,
                                            "message": "All 6 files in report package have been signed by submitter (EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk).",
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            # "/checkupload/{aid}/{dig}":{"get":{"tags":["default"],
            #                     "summary":"Given an AID and DIG returns information about the upload status",
            #                     "parameters":[{"in":"path","name":"aid","required":"true","schema":{"type":"string","minimum":1,"example":"EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk"},"description":"The AID"},
            #                                   {"in":"path","name":"dig","required":"true","schema":{"type":"string","minimum":1,"example":"EAPHGLJL1s6N4w1Hje5po6JPHu47R9-UoJqLweAci2LV"},"description":"The digest of the upload"}],
            #                     "responses":{"200":{"description":"OK","content":{"application/json":{"schema":{"type":"object","example":{
            #                                             "submitter": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk",
            #                                             "filename": "DUMMYLEI123456789012.IND_FR_IF010200_IFTM_2022-12-31_20220222134211000.zip",
            #                                             "status": "failed",
            #                                             "contentType": "application/zip",
            #                                             "size": 3390,
            #                                             "message": "No signatures found in manifest file"
            #                     }}}}}},
            #                     }},
            "/status/{aid}": {
                "get": {
                    "tags": ["default"],
                    "summary": "Given an AID returns information about the upload status",
                    "parameters": [
                        {
                            "in": "header",
                            "name": "Signature",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "example": 'indexed="?0";signify="0BAbJnlOwYCgQ-1SExPKoPR8AyF2luTrP207oFRSOqKNwpYIviOgA-Fp4Z11At2f3NWBwUbQRWEB8Tu3es1l_QUI"',
                            },
                            "description": "The signature of the data",
                        },
                        {
                            "in": "header",
                            "name": "Signature-Input",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "example": 'signify=("@method" "@path" "signify-resource" "signify-timestamp");created=1690386592;keyid="BPmhSfdhCPxr3EqjxzEtF8TVy0YX7ATo0Uc8oo2cnmY9";alg="ed25519"',
                            },
                            "description": "The signature of the data",
                        },
                        {
                            "in": "header",
                            "name": "Signify-Resource",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "example": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk",
                            },
                            "description": "The aid that siged the data",
                        },
                        {
                            "in": "header",
                            "name": "signify-timestamp",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "example": "2023-07-26T15:49:52.571000+00:00",
                            },
                            "description": "The timestamp of the data",
                        },
                        {
                            "in": "path",
                            "name": "aid",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "minimum": 1,
                                "example": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk",
                            },
                            "description": "The AID",
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "example": {
                                            "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk": [
                                                '{"submitter": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk", "filename": "test_MetaInfReportJson_noSigs.zip", "status": "failed", "contentType": "application/zip", "size": 3059, "message": "5 files from report package not signed {\'parameters.csv\', \'FilingIndicators.csv\', \'report.json\', \'i_10.01.csv\', \'i_10.02.csv\'}, []"}',
                                                '{"submitter": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk", "filename": "test_ifclass3.zip", "status": "verified", "contentType": "application/zip", "size": 5662, "message": "All 9 files in report package have been signed by submitter (EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk)."}',
                                                '{"submitter": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk", "filename": "test_ifgroup2023.zip", "status": "verified", "contentType": "application/zip", "size": 4467, "message": "All 6 files in report package have been signed by submitter (EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk)."}',
                                            ]
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/verify/header": {
                "get": {
                    "tags": ["default"],
                    "summary": "returns if the headers are properly signed",
                    "parameters": [
                        {
                            "in": "header",
                            "name": "Signature",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "example": 'indexed="?0";signify="0BB86jS2w9PKL1t-5hZIxgF9-vMNz4DsoASJR_f-u8FvnywdvosPOqbXUo97LuS-pYH_K_BPpfA2Y0XsGb2pSBoL"',
                            },
                            "description": "The signature of the data",
                        },
                        {
                            "in": "header",
                            "name": "Signature-Input",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "example": 'signify=("@method" "@path" "signify-resource" "signify-timestamp");created=1690922901;keyid="BPmhSfdhCPxr3EqjxzEtF8TVy0YX7ATo0Uc8oo2cnmY9";alg="ed25519"',
                            },
                            "description": "The signature of the data",
                        },
                        {
                            "in": "header",
                            "name": "Signify-Resource",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "example": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk",
                            },
                            "description": "The signature of the data",
                        },
                        {
                            "in": "header",
                            "name": "Signify-Timestamp",
                            "required": "true",
                            "schema": {
                                "type": "string",
                                "example": "2023-08-01T20:48:21.885000+00:00",
                            },
                            "description": "The signature of the data",
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object", "example": {}}
                                }
                            },
                        }
                    },
                }
            },
        },
    }

    doc = api_doc(
        app, config=config, url_prefix="/api/doc", title="API doc", editor=True
    )
    return doc


def falcon_app():
    app = falcon.App(
        middleware=falcon.CORSMiddleware(
            allow_origins="*",
            allow_credentials="*",
            expose_headers=[
                "cesr-attachment",
                "cesr-date",
                "content-type",
                "signature",
                "signature-input",
                "signify-resource",
                "signify-timestamp",
            ],
        )
    )
    if os.getenv("ENABLE_CORS", "false").lower() in ("true", "1"):
        print("CORS  enabled")
        app.add_middleware(middleware=HandleCORS())
    app.req_options.media_handlers.update(media.Handlers())
    app.resp_options.media_handlers.update(media.Handlers())

    # the signature is a keri cigar objects
    verCig = VerifySignedHeaders()

    app.add_route(ROUTE_PING, PingResource())
    app.add_route(ROUTE_LOGIN, LoginTask())
    app.add_route(f"{ROUTE_CHECK_LOGIN}"+"/{aid}", LoginTask())
    app.add_route(f"{ROUTE_UPLOAD}"+"/{aid}/{dig}", UploadTask(verCig))
    app.add_route(f"{ROUTE_CHECK_UPLOAD}"+"/{aid}/{dig}", UploadTask(verCig))
    app.add_route(f"{ROUTE_STATUS}"+"/{aid}", StatusTask(verCig))

    swagger_ui(app)

    return app


app = falcon_app()


def main():
    print("Starting RegPS...")
    return app


if __name__ == "__main__":
    main()
