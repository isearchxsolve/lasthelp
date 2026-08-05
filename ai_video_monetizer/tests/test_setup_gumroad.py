"""Tests for scripts/setup_gumroad.py."""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open, call
import pytest

os.environ["GUMROAD_ACCESS_TOKEN"] = "test_gumroad_token_12345"

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
if "scripts.setup_gumroad" in sys.modules:
    del sys.modules["scripts.setup_gumroad"]
from scripts import setup_gumroad


class TestModuleLevel:
    def test_access_token_loaded(self):
        assert setup_gumroad.ACCESS_TOKEN == "test_gumroad_token_12345"

    def test_base_url(self):
        assert setup_gumroad.BASE_URL == "https://api.gumroad.com/v2"

    def test_headers(self):
        assert "Authorization" in setup_gumroad.HEADERS
        assert "test_gumroad_token_12345" in setup_gumroad.HEADERS["Authorization"]
        assert setup_gumroad.HEADERS["Content-Type"] == "application/x-www-form-urlencoded"

    def test_products_structure(self):
        assert len(setup_gumroad.PRODUCTS) >= 1
        for product in setup_gumroad.PRODUCTS:
            assert "name" in product
            assert "price" in product


class TestApiCall:
    def test_get_success(self):
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {"success": True}
            result = setup_gumroad.api_call("GET", "/products")
            assert result == {"success": True}

    def test_post_success(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 201
            mock_post.return_value.json.return_value = {"success": True}
            result = setup_gumroad.api_call("POST", "/products", {"name": "test"})
            assert result == {"success": True}

    def test_api_error_status(self, capsys):
        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 400
            mock_get.return_value.text = "Bad Request"
            result = setup_gumroad.api_call("GET", "/products")
            assert result is None
            captured = capsys.readouterr()
            assert "API Error" in captured.out

    def test_network_error(self, capsys):
        with patch("requests.get", side_effect=Exception("connection refused")):
            result = setup_gumroad.api_call("GET", "/products")
            assert result is None
            captured = capsys.readouterr()
            assert "failed" in captured.out


class TestCreateProduct:
    def test_success(self):
        product = setup_gumroad.PRODUCTS[0]
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 201
            mock_post.return_value.json.return_value = {"success": True, "product": {"id": "prod_123"}}
            with patch("pathlib.Path.exists", return_value=True):
                with patch("builtins.open", mock_open(read_data=b"test")):
                    result = setup_gumroad.create_product(product)
                    assert result == "prod_123"

    def test_api_failure(self):
        product = setup_gumroad.PRODUCTS[0]
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 400
            mock_post.return_value.text = "error"
            result = setup_gumroad.create_product(product)
            assert result is None

    def test_file_not_found(self, capsys):
        product = setup_gumroad.PRODUCTS[0]
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 201
            mock_post.return_value.json.return_value = {"success": True, "product": {"id": "id"}}
            with patch("pathlib.Path.exists", return_value=False):
                result = setup_gumroad.create_product(product)
                assert result is "id"
                captured = capsys.readouterr()
                assert "File not found" in captured.out


class TestUploadFile:
    def test_success(self, capsys):
        with patch("builtins.open", mock_open(read_data=b"data")):
            with patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {"success": True}
                setup_gumroad.upload_file("prod_123", "file.pdf")

    def test_failure(self, capsys):
        with patch("builtins.open", mock_open(read_data=b"data")):
            with patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 400
                mock_post.return_value.text = "error"
                setup_gumroad.upload_file("prod_123", "file.pdf")
                captured = capsys.readouterr()
                assert "Upload failed" in captured.out

    def test_exception(self, capsys):
        with patch("builtins.open", mock_open(read_data=b"data")):
            with patch("requests.post", side_effect=Exception("upload failed")):
                with pytest.raises(Exception):
                    setup_gumroad.upload_file("prod_123", "file.pdf")


class TestCreateOrderBump:
    def test_success(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"success": True}
            result = setup_gumroad.create_order_bump("main_123", "bump_456")
            assert result["success"] is True

    def test_failure(self):
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 400
            mock_post.return_value.text = "error"
            result = setup_gumroad.create_order_bump("main_123", "bump_456")
            assert result is None


class TestSetupEmailSequence:
    def test_returns_sequence_list(self, capsys):
        result = setup_gumroad.setup_email_sequence("prod_123")
        assert isinstance(result, list)
        assert len(result) == 4
        assert result[0]["delay_hours"] == 0

    def test_displays_emails(self, capsys):
        setup_gumroad.setup_email_sequence("prod_123")
        captured = capsys.readouterr()
        assert "email sequence" in captured.out.lower() or "email" in captured.out.lower()


class TestMain:
    def _setup_basic_mocks(self):
        """Common mocks for main function paths."""
        return patch("scripts.setup_gumroad.api_call", return_value={
            "user": {"name": "TestUser", "email": "test@test.com"}
        })

    def test_main_success(self):
        with self._setup_basic_mocks():
            with patch("scripts.setup_gumroad.create_product", side_effect=["p1", "p2", "p3"]):
                with patch("scripts.setup_gumroad.create_order_bump", return_value={"success": True}):
                    with patch("scripts.setup_gumroad.setup_email_sequence", return_value=[]):
                        with patch("builtins.input", return_value=""):
                            setup_gumroad.main()

    def test_main_no_products_created(self):
        with self._setup_basic_mocks():
            with patch("scripts.setup_gumroad.create_product", return_value=None):
                with patch("builtins.input", return_value=""):
                    setup_gumroad.main()

    def test_main_some_products_created(self):
        with self._setup_basic_mocks():
            with patch("scripts.setup_gumroad.create_product", side_effect=["p1", None, None]):
                with patch("scripts.setup_gumroad.create_order_bump", return_value={"success": True}):
                    with patch("scripts.setup_gumroad.setup_email_sequence", return_value=[]):
                        with patch("builtins.input", return_value=""):
                            setup_gumroad.main()

    def test_main_auth_failure(self):
        with patch("scripts.setup_gumroad.api_call", return_value=None):
            with pytest.raises(SystemExit):
                setup_gumroad.main()

    def test_main_creation_exception(self):
        with self._setup_basic_mocks():
            with patch("scripts.setup_gumroad.create_product", side_effect=Exception("fail")):
                with pytest.raises(Exception):
                    with patch("builtins.input", return_value=""):
                        setup_gumroad.main()
