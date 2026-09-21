from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

import httpx

import service_gateway


class ServiceGatewayTests(unittest.TestCase):
    @patch("service_gateway.api_key", return_value="chave")
    @patch("service_gateway.api_base_url", return_value="https://api.example")
    @patch("service_gateway.httpx.request")
    def test_request_adds_authentication_and_surfaces_api_detail(self, request, _url, _key):
        response = httpx.Response(
            409,
            json={"detail": "registro duplicado"},
            request=httpx.Request("POST", "https://api.example/item"),
        )
        request.return_value = response
        with self.assertRaisesRegex(service_gateway.ApiClientError, "registro duplicado"):
            service_gateway._request("POST", "/item")
        self.assertEqual(request.call_args.kwargs["headers"]["X-API-Key"], "chave")

    @patch("service_gateway._request")
    @patch("service_gateway.remote_api_enabled", return_value=True)
    def test_remote_dashboard_restores_dates_expected_by_streamlit(self, _enabled, request):
        request.return_value = {
            "athletes": [{"id_atleta": 1, "data_nascimento": "2000-01-02"}],
            "measurements": [{"id_atleta": 1, "data": "2026-09-18"}],
        }
        athletes, measurements = service_gateway.load_player_dashboard()
        self.assertEqual(athletes[0]["data_nascimento"], date(2000, 1, 2))
        self.assertEqual(measurements[0]["data"], date(2026, 9, 18))

    @patch(
        "service_gateway._request",
        return_value={
            "minimum_temperature": 26.8,
            "maximum_temperature": 34.6,
        },
    )
    @patch("service_gateway.remote_api_enabled", return_value=True)
    def test_remote_temperature_scale_uses_upload_endpoint(self, _enabled, request):
        result = service_gateway.extract_thermography_scale(b"imagem")
        self.assertEqual(result["maximum_temperature"], 34.6)
        self.assertEqual(
            request.call_args.args,
            ("POST", "/api/v1/thermography/scale"),
        )
        self.assertEqual(
            request.call_args.kwargs["files"]["file"][1], b"imagem"
        )

    @patch("service_gateway._request", return_value={"id_atleta": 8})
    @patch("service_gateway.remote_api_enabled", return_value=True)
    def test_remote_athlete_create_serializes_birth_date(self, _enabled, request):
        result = service_gateway.create_athlete(name="Ana", birth_date=date(2000, 1, 2))
        self.assertEqual(result, 8)
        self.assertEqual(request.call_args.kwargs["json"]["birth_date"], "2000-01-02")


if __name__ == "__main__":
    unittest.main()
