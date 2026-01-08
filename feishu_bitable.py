import requests
from typing import Dict, Any, List, Optional


class FeishuBitableClient:
    def __init__(
        self,
        app_id: str,
        app_secret: str,
        bitable_app_token: str,
        bitable_table_id: str,
        timeout: int = 20,
    ):
        self._app_id = app_id
        self._app_secret = app_secret
        self._bitable_app_token = bitable_app_token
        self._bitable_table_id = bitable_table_id
        self._timeout = timeout
        self._token: Optional[str] = None

    def get_records_in_order(self) -> List[Dict[str, Any]]:
        """
        拉取整张多维表的所有 records（按 API 返回的自然顺序）。
        用于全表扫描、去重、找最后有效记录、找空行。
        """
        url = (
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self._bitable_app_token}"
            f"/tables/{self._bitable_table_id}/records"
        )

        items: List[Dict[str, Any]] = []
        page_token: Optional[str] = None

        while True:
            params: Dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token

            resp = requests.get(url, headers=self._headers(), params=params, timeout=self._timeout)
            data = resp.json()

            if resp.status_code >= 400 or data.get("code") != 0:
                raise RuntimeError({"http": resp.status_code, "body": data})

            chunk = data.get("data", {}).get("items", [])
            items.extend(chunk)

            page_token = data.get("data", {}).get("page_token")
            if not page_token:
                break

        return items

    def get_tenant_access_token(self) -> str:
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        resp = requests.post(
            url,
            json={"app_id": self._app_id, "app_secret": self._app_secret},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(data)
        self._token = data["tenant_access_token"]
        return self._token

    def _headers(self) -> Dict[str, str]:
        if not self._token:
            self.get_tenant_access_token()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def create_record(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        url = (
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self._bitable_app_token}"
            f"/tables/{self._bitable_table_id}/records"
        )
        resp = requests.post(url, headers=self._headers(), json={"fields": fields}, timeout=self._timeout)
        data = resp.json()
        if resp.status_code >= 400 or data.get("code") != 0:
            raise RuntimeError({"http": resp.status_code, "body": data})
        return data

    def update_record(self, record_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """覆盖更新某条记录（用于把空行 record 覆盖成有效数据）"""
        url = (
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self._bitable_app_token}"
            f"/tables/{self._bitable_table_id}/records/{record_id}"
        )
        resp = requests.put(url, headers=self._headers(), json={"fields": fields}, timeout=self._timeout)
        data = resp.json()
        if resp.status_code >= 400 or data.get("code") != 0:
            raise RuntimeError({"http": resp.status_code, "body": data})
        return data
