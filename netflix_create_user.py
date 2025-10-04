# create_profile_with_state.py (compatível com versões antigas)
import json
from playwright.sync_api import sync_playwright

STATE_PATH = "netflix_state.json"
GRAPHQL_URL = "https://web.prod.cloud.netflix.com/graphql"

PERSISTED_QUERY_ID = "cca89a76-1986-49a9-9c8f-afaa2c098ead"
PERSISTED_QUERY_VERSION = 102

def main(name="vinicius", avatar_key="icon26", is_kids=False):
    payload = {
        "operationName": "AddProfile",
        "variables": {
            "name": name,
            "avatarKey": avatar_key,
            "isKids": bool(is_kids),
        },
        "extensions": {
            "persistedQuery": {
                "id": PERSISTED_QUERY_ID,
                "version": PERSISTED_QUERY_VERSION
            }
        }
    }

    body = json.dumps(payload)  # <- serializa manualmente

    with sync_playwright() as p:
        req = p.request.new_context(
            storage_state=STATE_PATH,
            extra_http_headers={
                "origin": "https://www.netflix.com",
                "referer": "https://www.netflix.com/",
                "x-netflix.context.operation-name": "AddProfile",
                "content-type": "application/json",  # <- importante com data=
            },
        )

        resp = req.post(GRAPHQL_URL, data=body)  # <- usa data= em vez de json=
        print("HTTP", resp.status)
        try:
            print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
        except Exception:
            print(resp.text())

        req.dispose()

if __name__ == "__main__":
    main()