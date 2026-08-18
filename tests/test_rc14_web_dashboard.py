import http.client
import inspect
import json
import socket
import threading
import time
import unittest
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import patch

from src.ui.contracts import VisualFrameDTO
from src.ui.dashboard.professional_contracts import (DashboardPhotoDTO,
    DashboardSnapshotDTO,RecentAttendanceRowDTO,RecentRecognitionRowDTO)
from src.ui.web_dashboard import (LatestPresentationFrameStore,
    WebDashboardController,WebDashboardServer)
from src.ui.web_dashboard.contracts import WebDashboardPolicy


def free_port():
    value=socket.socket();value.bind(("127.0.0.1",0));port=value.getsockname()[1];value.close();return port


def snapshot(camera="Desconectada"):
    photo=DashboardPhotoDTO(True,1,1,"JPEG",b"photo")
    return DashboardSnapshotDTO(2,3,4,1,(RecentRecognitionRowDTO(photo,"Ada","10:00",.91),),(RecentAttendanceRowDTO(photo,"Ada","08:00",None,"PRESENT"),),camera,"OK",7,"Activo","Activa",datetime.now(timezone.utc))


class WebDashboardTests(unittest.TestCase):
    def setUp(self):
        self.store=LatestPresentationFrameStore();self.controller=WebDashboardController(lambda:snapshot(),camera_provider=lambda:{"state":"disconnected","name":"Jetson Cam","type":"RTSP","source":"rtsp://user:secret@camera.local/stream"})
        self.port=free_port();self.policy=WebDashboardPolicy(True,"127.0.0.1",self.port,False,False,10,75,1)
        self.server=WebDashboardServer(self.policy,self.controller,self.store,printer=lambda _value:None)
        self.assertTrue(self.server.start())
    def tearDown(self):self.server.close();self.store.close()
    def request(self,method,path):
        connection=http.client.HTTPConnection("127.0.0.1",self.port,timeout=2);connection.request(method,path);response=connection.getresponse();body=response.read();headers=dict(response.getheaders());connection.close();return response.status,headers,body

    def test_dashboard_json_pages_disconnected_camera_and_no_biometrics(self):
        status,headers,body=self.request("GET","/api/dashboard");self.assertEqual(status,200)
        value=json.loads(body);self.assertEqual(value["statistics"]["people_present"],2);self.assertEqual(len(value["recent_recognitions"]),1)
        self.assertEqual(value["camera"],"Desconectada");self.assertNotIn("secret",body.decode());self.assertIn("rtsp://***:***@",body.decode())
        lowered=body.decode().lower()
        for forbidden in ("embedding","template","password","hash","salt","rgb_bytes","person_id"):self.assertNotIn(forbidden,lowered)
        for path in ("/","/people","/history","/attendance","/reports","/system"):
            page_status,_,_=self.request("GET",path);self.assertIn(page_status,(200,503))
        self.assertEqual(headers["X-Content-Type-Options"],"nosniff");self.assertIn("Content-Security-Policy",headers);self.assertEqual(headers["Cache-Control"],"no-store");self.assertNotIn("Access-Control-Allow-Origin",headers)

    def test_methods_directory_and_thumbnail_traversal_are_rejected(self):
        for method in ("POST","PUT","DELETE","PATCH","OPTIONS"):
            status,headers,_=self.request(method,"/");self.assertEqual(status,405);self.assertEqual(headers["Allow"],"GET")
        for path in ("/api/thumbnails/..%2Fsecret","/api/thumbnails/%2Fetc%2Fpasswd","/api/thumbnails/not-a-token","/unknown"):
            self.assertEqual(self.request("GET",path)[0],404)

    def test_no_frame_available_and_capacity_one_owned_copy(self):
        self.assertEqual(self.request("GET","/api/video.mjpeg")[0],503)
        payload=bytearray(b"\x01\x02\x03");frame=VisualFrameDTO(1,1,bytes(payload),1);self.store.publish(frame);payload[:]=b"xxx"
        self.store.publish(VisualFrameDTO(1,1,b"\x04\x05\x06",2));self.assertEqual(self.store.latest().sequence_id,2);self.assertEqual(self.store.latest().rgb_bytes,b"\x04\x05\x06")

    def test_stream_client_limit_and_shutdown_terminates_stream(self):
        self.store.publish(VisualFrameDTO(1,1,b"\x04\x05\x06",1));self.assertTrue(self.server._streams.acquire(False))
        self.assertEqual(self.request("GET","/api/video.mjpeg")[0],503);self.server._streams.release()
        connection=http.client.HTTPConnection("127.0.0.1",self.port,timeout=3);connection.request("GET","/api/video.mjpeg");response=connection.getresponse();self.assertEqual(response.status,200);response.read(64)
        worker=threading.Thread(target=self.server.close);worker.start();worker.join(3);self.assertFalse(worker.is_alive());connection.close();self.assertFalse(self.server.running)

    def test_browser_failure_is_safe_ip_display_and_no_camera_construction(self):
        self.server.close();messages=[]
        server=WebDashboardServer(WebDashboardPolicy(True,"127.0.0.1",self.port,True,False,10,75,1),self.controller,self.store,browser_open=lambda _url:(_ for _ in ()).throw(OSError()),printer=messages.append)
        with patch("src.ui.web_dashboard.http_server.detect_lan_ip",return_value="192.168.1.50"):self.assertTrue(server.start())
        server.close();self.assertIn("Local: http://127.0.0.1",messages[1]);self.assertTrue(any("192.168.1.50" in item for item in messages))
        source="".join(inspect.getsource(value) for value in (WebDashboardServer,WebDashboardController,LatestPresentationFrameStore))
        self.assertNotIn("VideoCapture",source);self.assertNotIn("CameraManager",source)


if __name__=="__main__":unittest.main()
