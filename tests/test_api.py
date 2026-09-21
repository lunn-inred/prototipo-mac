from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from athlete_service import AthleteInUseError
from mac_api.main import app
from settings import api_key
from thermography_service import DuplicateThermographyError


class ApiInfrastructureTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_and_openapi_are_available(self):
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(schema["info"]["title"], "MAC Performance API")
        self.assertIn("/api/v1/athletes", schema["paths"])

    def test_api_key_is_optional_but_enforced_when_configured(self):
        with patch("mac_api.main.api_key", return_value="segredo"), patch(
            "mac_api.main.data_repository.list_athletes", return_value=[]
        ):
            self.assertEqual(self.client.get("/api/v1/athletes").status_code, 401)
            response = self.client.get(
                "/api/v1/athletes", headers={"X-API-Key": "segredo"}
            )
        self.assertEqual(response.status_code, 200)


class AthleteApiTests(unittest.TestCase):
    def setUp(self):
        key = api_key()
        headers = {"X-API-Key": key} if key else {}
        self.client = TestClient(app, headers=headers)

    @patch("mac_api.main.data_repository.list_athletes")
    def test_lists_athletes(self, list_athletes):
        list_athletes.return_value = [{"id_atleta": 7, "nome": "Ana"}]
        response = self.client.get("/api/v1/athletes")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["id_atleta"], 7)

    @patch("mac_api.main.create_athlete", return_value=9)
    def test_creates_athlete(self, create):
        response = self.client.post(
            "/api/v1/athletes",
            json={"name": " Ana ", "nickname": "Aninha", "birth_date": "2000-01-02"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"id_atleta": 9})
        create.assert_called_once_with(
            name=" Ana ", nickname="Aninha", position=None, group=None,
            birth_date=date(2000, 1, 2),
        )

    @patch("mac_api.main.delete_athlete", side_effect=AthleteInUseError("em uso"))
    def test_maps_athlete_in_use_to_conflict(self, _delete):
        response = self.client.delete("/api/v1/athletes/2")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "em uso")


class MeasurementApiTests(unittest.TestCase):
    def setUp(self):
        key = api_key()
        headers = {"X-API-Key": key} if key else {}
        self.client = TestClient(app, headers=headers)

    @patch("mac_api.main.data_repository.jump_records", return_value=[])
    @patch("mac_api.main.data_repository.gps_records", return_value=[])
    @patch("mac_api.main.data_repository.player_dashboard_data", return_value={"athletes": [], "measurements": []})
    def test_read_endpoints(self, _dashboard, _gps, _jumps):
        self.assertEqual(self.client.get("/api/v1/players/dashboard").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/jumps").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/gps").status_code, 200)

    @patch("mac_api.main.extract_thermography_scale")
    def test_extracts_thermography_scale_without_storing_image(self, extract):
        extract.return_value = {
            "minimum_temperature": 26.8,
            "maximum_temperature": 34.6,
        }
        response = self.client.post(
            "/api/v1/thermography/scale",
            files={"file": ("frente.jpg", b"imagem", "image/jpeg")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["minimum_temperature"], 26.8)
        extract.assert_called_once_with(b"imagem")

    @patch("mac_api.main.analyze_thermography_view")
    def test_analyzes_uploaded_thermography_without_storing_image(self, analyze):
        analyze.return_value = {"view": "front", "boxes": {}, "metrics": {}}
        response = self.client.post(
            "/api/v1/thermography/analyze",
            files={"file": ("frente.jpg", b"imagem", "image/jpeg")},
            data={
                "view": "front", "minimum_temperature": "20",
                "maximum_temperature": "40", "threshold": "36",
            },
        )
        self.assertEqual(response.status_code, 200)
        analyze.assert_called_once_with(
            b"imagem", view="front", minimum_temperature=20.0,
            maximum_temperature=40.0, threshold=36.0,
        )

    @patch("mac_api.main.save_image_thermography", side_effect=DuplicateThermographyError("duplicada"))
    def test_maps_duplicate_thermography_to_conflict(self, _save):
        response = self.client.post(
            "/api/v1/thermography",
            json={
                "athlete_id": 1, "collected_at": "2026-09-18T10:00:00",
                "mass": 70, "pain_score": 2, "front_right": 1,
                "front_left": 2, "back_right": 3, "back_left": 4,
            },
        )
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
