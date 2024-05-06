import time
from .tasks import check_login, check_upload, upload, verify_vlei, verify_cig
import falcon
from falcon import media
from falcon.http_status import HTTPStatus
import json
from keri.end import ending
import os
from swagger_ui import api_doc

uploadStatus = {}

def initStatusDb(aid):
    if(aid not in uploadStatus):
        print("Initialized status db for {}".format(aid))
        uploadStatus[aid] = []
    else:
        print("Status db already initialized for {}".format(aid))

#the signature is a keri cigar objects
class VerifySignedHeaders:

    DefaultFields = ["Signify-Resource",
                     "@method",
                     "@path",
                     "Signify-Timestamp"]

    def process_request(self, req, resp):
        print(f"Processing signed header verification request {req}")
        aid, cig, ser = self.handle_headers(req)
        vresp = verify_cig(aid, cig, ser)
        print(f"VerifySignedHeaders.on_post: response {vresp}")

        if vresp.status_code >= 400:
            print(f"Header verification failed request {vresp.status_code} {vresp.text} {vresp.headers}")
        else :
            print(f"Signed header verification succeeded {resp}")
            initStatusDb(aid)

        resp.status = falcon.code_to_http_status(vresp.status_code)
        resp.text = vresp.text
        resp.content_type = vresp.headers['Content-Type']

    def on_get(self, req, resp):
        return self.process_request(req, resp)

    def handle_headers(self, req):
        print(f"processing header req {req}")

        headers = req.headers
        if "SIGNATURE-INPUT" not in headers or "SIGNATURE" not in headers:
            return False

        siginput = headers["SIGNATURE-INPUT"]
        if not siginput:
            return False
        signature = headers["SIGNATURE"]
        if not signature:
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

            params = ';'.join(values)

            items.append(f'"@signature-params: {params}"')
            ser = "\n".join(items)

            signages = ending.designature(signature)
            cig = signages[0].markers[inputage.name]
            assert len(signages) == 1
            assert signages[0].indexed is False
            assert "signify" in signages[0].markers

            aid = req.headers['SIGNIFY-RESOURCE']
            sig = cig.qb64
            print(f"verification input aid={aid} ser={ser} cig={sig}")
            return aid, sig, ser

class LoginTask:

    # Expects a JSON object with the following fields:
    # - said: the SAID of the credential
    # - vlei: the vLEI ECR CESR
    def on_post(self, req, resp):
        print("LoginTask.on_post")
        try:
            if req.content_type not in ("application/json",):
                raise falcon.HTTPBadRequest(description=f"invalid content type={req.content_type} for VC presentation, should be application/json")

            data = req.media
            if data.get("said") is None:
                raise falcon.HTTPBadRequest(description="requests with a said is required")
            if data.get("vlei") is None:
                raise falcon.HTTPBadRequest(description="requests with vlei ecr cesr is required")



            # raw_json = req.stream.read()
            # data = json.loads(raw_json)

            # ims = req.bounded_stream.read()
            # data = ims.decode("utf-8")
            print(f"LoginTask.on_post: sending login cred {str(data)[:50]}...")
            
            result = verify_vlei(data['said'], data['vlei'])

            print(f"LoginTask.on_post: received data {result.status_code}")

            resp.status = falcon.code_to_http_status(result.status_code)
            resp.text = result.text
            resp.content_type = result.headers['Content-Type']
        except Exception as e:
            print(f"LoginTask.on_post: Exception: {e}")
            resp.text = f"Exception: {e}"
            resp.status = falcon.HTTP_500
            
    def on_get(self, req, resp, aid):
        print("LoginTask.on_get")
        try:
            print(f"LoginTask.on_get: sending aid {aid}")
            login_resp = check_login(aid)
            # if resp.status != falcon.HTTP_OK:
            #     login_response = None
            #     tries=0
            #     while(tries < 5 and (login_response == None or login_response.status_code == falcon.http_status_to_code(falcon.HTTP_404))):
            #         login_response = check_login(aid)
            #         print(f"polling result {login_response}")
            #         tries += 1
            #         time.sleep (1)
            #     print(f"LoginTask.on_get: received data {resp.text[:50]}")
            #     return login_response
            resp.status = login_resp.status_code
            resp.text = login_resp.text
        except Exception as e:
            print(f"LoginTask.on_get: Exception: {e}")
            resp.text = f"Exception: {e}"
            resp.status = falcon.HTTP_500
            
class UploadTask:
    
    def __init__(self, verCig: VerifySignedHeaders) -> None:
        self.verCig = verCig
        
    def on_post(self, req, resp, aid, dig):
        print("UploadTask.on_post {}".format(req))
        sig_check = self.verCig.process_request(req, resp)
        if sig_check:
            print(f"UploadTask.on_post: Invalid signature on headers")
            return sig_check
        try:
            raw = req.bounded_stream.read()
            print(f"UploadTask.on_post: request for {aid} {dig} {raw} {req.content_type}")
            result = upload(aid, dig, req.content_type, raw)
            print(f"UploadTask.on_post: received data {result}")

            resp.status = falcon.code_to_http_status(result.status_code)
            resp.text = result.text
            resp.content_type = result.headers['Content-Type']
            # add to status dict
            if(aid not in uploadStatus):
                print(f"UploadTask.on_post: Error aid not logged in {aid}")
                resp.text = f"AID not logged in: {aid}"
                resp.status = falcon.HTTP_401    
            else:    
                print(f"UploadTask.on_post added uploadStatus for {aid}: {dig}")
                uploadStatus[f"{aid}"].append(json.loads(resp.text))
        except Exception as e:
            print(f"UploadTask.on_post: Exception: {e}")
            resp.text = f"Exception: {e}"
            resp.status = falcon.HTTP_500
            
    def on_get(self, req, resp, aid, dig):
        print("UploadTask.on_get")
        sig_check = self.verCig.process_request(req, resp)
        if sig_check:
            print(f"UploadTask.on_post: Invalid signature on headers")
            return sig_check
        try:
            print(f"UploadTask.on_get: sending aid {aid} for dig {dig}")
            result = check_upload(aid, dig)
            print(f"UploadTask.on_get: received data {result}")
            resp.status = falcon.code_to_http_status(result.status_code)
            resp.text = result.text
            resp.content_type = result.headers['Content-Type']
        except Exception as e:
            print(f"UploadTask.on_get: Exception: {e}")
            resp.text = f"Exception: {e}"
            resp.status = falcon.HTTP_500

class StatusTask:
    
    def __init__(self, verCig: VerifySignedHeaders) -> None:
        self.verCig = verCig   
             
    def on_get(self, req, resp, aid):
        print(f"StatusTask.on_get request {req}")
        sig_check = self.verCig.process_request(req, resp)
        if sig_check:
            print(f"UploadTask.on_post: Invalid signature on headers")
            return sig_check
        try:
            print(f"StatusTask.on_get: aid {aid}")
            if(aid not in uploadStatus):
                print(f"UploadTask.on_post: Cannot find status for {aid}")
                resp.text = f"AID not logged in: {aid}"
                resp.status = falcon.HTTP_401
            else:
                result = uploadStatus[f"{aid}"]
                print(f"StatusTask.on_get: received data {result}")
                resp.status = falcon.HTTP_200
                resp.text = json.dumps({f"{aid}":result})
                if not result:
                    print(f"Empty upload status list for aid {aid}")
        except Exception as e:
            print(f"StatusTask.on_get: Exception: {e}")
            resp.text = f"Exception: {e}"
            resp.status = falcon.HTTP_500

class HandleCORS(object):
    def process_request(self, req, resp):
        resp.set_header('Access-Control-Allow-Origin', '*')
        resp.set_header('Access-Control-Allow-Methods', '*')
        resp.set_header('Access-Control-Allow-Headers', '*')
        resp.set_header('Access-Control-Max-Age', 1728000)  # 20 days
        if req.method == 'OPTIONS':
            raise HTTPStatus(falcon.HTTP_200, text='\n')

class PingResource:
   def on_get(self, req, resp):
      """Handles GET requests"""
      resp.status = falcon.HTTP_200
      resp.content_type = falcon.MEDIA_TEXT
      resp.text = (
         'Pong'
      )

def getRequiredParam(body, name):
    param = body.get(name)
    if param is None:
        raise falcon.HTTPBadRequest(description=f"required field '{name}' missing from request")

    return param

def swagger_ui(app):
    vlei_contents = None
    with open('app/data/credential.cesr', 'r') as cfile:
        vlei_contents = cfile.read()

    report_zip = None
    with open('./data/report.zip', 'rb') as rfile:        
        report_zip = rfile

    config = {"openapi":"3.0.1",
            "info":{"title":"Regulator portal service api","description":"Regulator web portal service api","version":"1.0.0"},
            "servers":[{"url":"http://127.0.0.1:8000","description":"local server"}],
            "tags":[{"name":"default","description":"default tag"}],
            "paths":{"/ping":{"get":{"tags":["default"],"summary":"output pong.","responses":{"200":{"description":"OK","content":{"application/text":{"schema":{"type":"object","example":"Pong"}}}}}}},
                    "/login":{"post":{"tags":["default"],
                                        "summary":"Given an AID and vLEI, returns information about the login",
                                        "requestBody":{"required":"true","content":{"application/json":{"schema":{"type":"object","properties":{
                                            "aid":{"type":"string","example":"EHYfRWfM6RxYbzyodJ6SwYytlmCCW2gw5V-FsoX5BgGx"},
                                            "said":{"type":"string","example":"EH37Qxg6UJF_gboIFAlvqdOu7r6Tz7P7BrVAeyHo_WDL"},
                                            "vlei":{"type":"string","example":f"{vlei_contents}"}
                                            }}}}},
                                        "responses":{"200":{"description":"OK","content":{"application/json":{"schema":{"type":"object","example":{
                                            "aid": "EHYfRWfM6RxYbzyodJ6SwYytlmCCW2gw5V-FsoX5BgGx",
                                            "said": "EH37Qxg6UJF_gboIFAlvqdOu7r6Tz7P7BrVAeyHo_WDL"
                                            }}}}}},
                                        }},
                    "/checklogin/{aid}":{"get":{"tags":["default"],
                                        "summary":"Given an AID returns information about the login",
                                        "parameters":[{"in":"path","name":"aid","required":"true","schema":{"type":"string","minimum":1,"example":"EHYfRWfM6RxYbzyodJ6SwYytlmCCW2gw5V-FsoX5BgGx"},"description":"The AID"}],
                                        "responses":{"200":{"description":"OK","content":{"application/json":{"schema":{"type":"object","example":{
                                            "aid": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk",
                                            "said": "EBdaAMrpqfB0PlTgI3juS8UFgIPAXC1NZd1jSk6acenf"
                                        }}}}}}
                                        }},
                    "/upload/{aid}/{dig}":{"post":{"tags":["default"],
                                        "summary":"Given an AID and DIG, returns information about the upload",
                                        "parameters":[
                                                    {"in":"path","name":"aid","required":"true","schema":{"type":"string","minimum":1,"example":"EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk"},"description":"The AID"},
                                                      {"in":"path","name":"dig","required":"true","schema":{"type":"string","minimum":1,"example":"EC7b6S50sY26HTj6AtQiWMDMucsBxMvThkmrKUBXVMf0"},"description":"The digest of the upload"},
                                                    {"in":"header","name":"Signature","required":"true",
                                                    "schema":{"type":"string","example":"indexed=\"?0\";signify=\"0BCLs_wv3X6YFoFhB7acH_BePXS7zjBJPvuChdr01cM60Igf_sxYsah9sLHP-pMSYFs1Y6zYUo58HVG8tRd4X1IC\""},
                                                    "description":"The signature of the data"},
                                                    {"in":"header","name":"Signature-Input","required":"true",
                                                    "schema":{"type":"string","example":"signify=(\"@method\" \"@path\" \"signify-resource\" \"signify-timestamp\");created=1690462814;keyid=\"BPmhSfdhCPxr3EqjxzEtF8TVy0YX7ATo0Uc8oo2cnmY9\";alg=\"ed25519\""},
                                                    "description":"The signature of the data"},
                                                    {"in":"header","name":"Signify-Resource","required":"true",
                                                    "schema":{"type":"string","example":"EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk"},
                                                    "description":"The aid that siged the data"},
                                                    {"in":"header","name":"signify-timestamp","required":"true",
                                                    "schema":{"type":"string","example":"2023-07-27T13:00:14.802000+00:00"},
                                                    "description":"The timestamp of the data"}  
                                                      ],
                                        "requestBody":{"required":"true","content":{"multipart/form-data":{"schema":{"type":"object","properties":{
                                            "upload":{"type":"string","format":"binary","example":f"{report_zip}"}
                                            }}}}},
                                        "responses":{"200":{"description":"OK","content":{"application/json":{"schema":{"type":"object","example":{
                                            "submitter": "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk",
                                            "filename": "test_ifgroup2023.zip",
                                            "status": "verified",
                                            "contentType": "application/zip",
                                            "size": 4467,
                                            "message": "All 6 files in report package have been signed by submitter (EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk)."
                                        }}}}}},
                                        }},
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
                    "/status/{aid}":{"get":{"tags":["default"],
                                        "summary":"Given an AID returns information about the upload status",
                                        "parameters":[
                                            {"in":"header","name":"Signature","required":"true",
                                             "schema":{"type":"string","example":"indexed=\"?0\";signify=\"0BAbJnlOwYCgQ-1SExPKoPR8AyF2luTrP207oFRSOqKNwpYIviOgA-Fp4Z11At2f3NWBwUbQRWEB8Tu3es1l_QUI\""},
                                             "description":"The signature of the data"},
                                            {"in":"header","name":"Signature-Input","required":"true",
                                             "schema":{"type":"string","example":"signify=(\"@method\" \"@path\" \"signify-resource\" \"signify-timestamp\");created=1690386592;keyid=\"BPmhSfdhCPxr3EqjxzEtF8TVy0YX7ATo0Uc8oo2cnmY9\";alg=\"ed25519\""},
                                             "description":"The signature of the data"},
                                            {"in":"header","name":"Signify-Resource","required":"true",
                                             "schema":{"type":"string","example":"EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk"},
                                             "description":"The aid that siged the data"},
                                            {"in":"header","name":"signify-timestamp","required":"true",
                                             "schema":{"type":"string","example":"2023-07-26T15:49:52.571000+00:00"},
                                             "description":"The timestamp of the data"},
                                            {"in":"path","name":"aid","required":"true",
                                             "schema":{"type":"string","minimum":1,"example":"EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk"},
                                             "description":"The AID"}
                                        ],
                                        "responses":{"200":{"description":"OK","content":{"application/json":{"schema":{"type":"object","example":{
                                            "EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk": [
                                                "{\"submitter\": \"EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk\", \"filename\": \"test_MetaInfReportJson_noSigs.zip\", \"status\": \"failed\", \"contentType\": \"application/zip\", \"size\": 3059, \"message\": \"5 files from report package not signed {'parameters.csv', 'FilingIndicators.csv', 'report.json', 'i_10.01.csv', 'i_10.02.csv'}, []\"}",
                                                "{\"submitter\": \"EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk\", \"filename\": \"test_ifclass3.zip\", \"status\": \"verified\", \"contentType\": \"application/zip\", \"size\": 5662, \"message\": \"All 9 files in report package have been signed by submitter (EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk).\"}",
                                                "{\"submitter\": \"EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk\", \"filename\": \"test_ifgroup2023.zip\", \"status\": \"verified\", \"contentType\": \"application/zip\", \"size\": 4467, \"message\": \"All 6 files in report package have been signed by submitter (EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk).\"}"
                                            ]
                                            }}}}}},
                                        }},
                    "/verify/header":{"get":{"tags":["default"],
                                        "summary":"returns if the headers are properly signed",
                                        "parameters":[
                                            {"in":"header","name":"Signature","required":"true",
                                             "schema":{"type":"string","example":"indexed=\"?0\";signify=\"0BB86jS2w9PKL1t-5hZIxgF9-vMNz4DsoASJR_f-u8FvnywdvosPOqbXUo97LuS-pYH_K_BPpfA2Y0XsGb2pSBoL\""},
                                             "description":"The signature of the data"},
                                            {"in":"header","name":"Signature-Input","required":"true",
                                             "schema":{"type":"string","example":"signify=(\"@method\" \"@path\" \"signify-resource\" \"signify-timestamp\");created=1690922901;keyid=\"BPmhSfdhCPxr3EqjxzEtF8TVy0YX7ATo0Uc8oo2cnmY9\";alg=\"ed25519\""},
                                             "description":"The signature of the data"},
                                            {"in":"header","name":"Signify-Resource","required":"true",
                                             "schema":{"type":"string","example":"EBcIURLpxmVwahksgrsGW6_dUw0zBhyEHYFk17eWrZfk"},
                                             "description":"The signature of the data"},
                                            {"in":"header","name":"Signify-Timestamp","required":"true",
                                             "schema":{"type":"string","example":"2023-08-01T20:48:21.885000+00:00"},
                                             "description":"The signature of the data"}
                                        ],
                                        "responses":{"200":{"description":"OK","content":{"application/json":{"schema":{"type":"object","example":{}}}}}},
                                        }},
                    }}

    doc = api_doc(app, config=config, url_prefix='/api/doc', title='API doc', editor=True)
    return doc

def falcon_app():    
    app = falcon.App(middleware=falcon.CORSMiddleware(
    allow_origins='*', allow_credentials='*',
    expose_headers=['cesr-attachment', 'cesr-date', 'content-type', 'signature', 'signature-input',
                    'signify-resource', 'signify-timestamp']))
    if os.getenv("ENABLE_CORS", "false").lower() in ("true", "1"):
        print("CORS  enabled")
        app.add_middleware(middleware=HandleCORS())
    app.req_options.media_handlers.update(media.Handlers())
    app.resp_options.media_handlers.update(media.Handlers())

    #the signature is a keri cigar objects
    verCig = VerifySignedHeaders()
    app.add_route("/verify/header", verCig)

    app.add_route('/ping', PingResource())
    app.add_route('/login', LoginTask())
    app.add_route("/checklogin/{aid}", LoginTask())
    app.add_route('/upload/{aid}/{dig}', UploadTask(verCig))
    app.add_route("/checkupload/{aid}/{dig}", UploadTask(verCig))
    app.add_route("/status/{aid}", StatusTask(verCig))
    
    return app
    
def main():
    print("Starting RegPS...")
    app = falcon_app()
    api_doc=swagger_ui(app)

    return app
    
if __name__ == '__main__':
    main()