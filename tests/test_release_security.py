"""Local API boundary checks: no requests to production services."""
import unittest
from fastapi.testclient import TestClient
from app.main import app

class ReleaseSecurityTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app)

    def test_registry_requires_authentication(self):
        for method,path,kwargs in [
            ('get','/api/orders/not-real',{}),
            ('delete','/api/orders/not-real',{}),
            ('patch','/api/orders/not-real',{'json':{'title':'changed'}}),
            ('post','/api/orders/',{'json':{'id':'ATTACK','number':'X','title':'X'}}),
            ('get','/api/orders/not-real/versions',{}),
        ]:
            with self.subTest(method=method,path=path):
                self.assertEqual(getattr(self.client,method)(path,**kwargs).status_code,401)

    def test_cors_rejects_untrusted_origin(self):
        response=self.client.options('/api/orders/',headers={
            'Origin':'https://attacker.invalid','Access-Control-Request-Method':'GET'})
        self.assertNotIn('access-control-allow-origin',response.headers)
        self.assertEqual(response.status_code,400)

    def test_anonymous_sql_payload_cannot_read_reports(self):
        for path in ('/api/reports/?program_id=%27%20OR%201=1--','/api/executions/?measure_id=%27%3BDROP%20TABLE%20users--'):
            self.assertEqual(self.client.get(path).status_code,401)
