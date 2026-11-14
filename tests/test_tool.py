"""Unit tests for tool/ package."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lib.security import (
    create_ack_payload,
    decrypt_payload,
    derive_key,
    encrypt_payload,
)
from tool.client import MeshClient
from tool.schemas import get_tool_schemas
from tool.tools import CommandMeshTools, get_tools


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock(spec=MeshClient)
    client.is_connected = True
    client.ensure_connected.return_value = True

    # Discovered devices
    devices = {
        "laptop": {
            "id": "laptop",
            "name": "Work Laptop",
            "type": "pc",
            "online": True,
            "capabilities": ["dpad_up", "press_keys", "run_script"],
        },
        "tv": {
            "id": "tv",
            "name": "Living Room TV",
            "type": "tv",
            "online": True,
            "capabilities": ["dpad_up", "home"],
        },
        "off_pc": {
            "id": "off_pc",
            "name": "Offline PC",
            "type": "pc",
            "online": False,
            "capabilities": ["dpad_up"],
        },
    }
    client.list_devices.return_value = list(devices.values())
    client.get_device.side_effect = lambda dev_id: devices.get(dev_id)

    # Default execute_command response
    client.execute_command.return_value = {
        "success": True,
        "device": "laptop",
        "action": "home",
        "result": "ok",
    }
    return client


@pytest.fixture
def tools(mock_client: MagicMock) -> CommandMeshTools:
    return CommandMeshTools(client=mock_client)


class TestToolDiscovery:
    """Test device discovery tools."""

    def test_list_devices(self, tools: CommandMeshTools) -> None:
        res = tools.list_devices()
        assert res["success"] is True
        ids = [d["id"] for d in res["devices"]]
        assert "laptop" in ids
        assert "tv" in ids

    def test_get_device_status_found(self, tools: CommandMeshTools) -> None:
        res = tools.get_device_status("laptop")
        assert res["success"] is True
        assert res["device"]["id"] == "laptop"

    def test_get_device_status_not_found(self, tools: CommandMeshTools) -> None:
        res = tools.get_device_status("nonexistent")
        assert res["success"] is False
        assert res["error"] == "device_not_found"


class TestToolDpad:
    """Test D-pad navigation tool."""

    @pytest.mark.parametrize("direction", ["up", "down", "left", "right", "center"])
    def test_valid_direction(
        self,
        tools: CommandMeshTools,
        mock_client: MagicMock,
        direction: str,
    ) -> None:
        tools.dpad("laptop", direction)
        mock_client.execute_command.assert_called_with(
            device_id="laptop",
            action=f"dpad_{direction}",
            data=None,
        )

    def test_dpad_aliases(
        self,
        tools: CommandMeshTools,
        mock_client: MagicMock,
    ) -> None:
        tools.dpad("tv", "ok")
        mock_client.execute_command.assert_called_with(
            device_id="tv",
            action="dpad_center",
            data=None,
        )

        tools.dpad("tv", "enter")
        mock_client.execute_command.assert_called_with(
            device_id="tv",
            action="dpad_center",
            data=None,
        )

    def test_invalid_direction(self, tools: CommandMeshTools) -> None:
        res = tools.dpad("laptop", "diagonal")
        assert res["success"] is False
        assert res["error"] == "invalid_parameter"


class TestToolMedia:
    """Test media control tool."""

    @pytest.mark.parametrize("action", ["play_pause", "vol_up", "vol_down"])
    def test_valid_media(
        self,
        tools: CommandMeshTools,
        mock_client: MagicMock,
        action: str,
    ) -> None:
        tools.media_control("tv", action)
        mock_client.execute_command.assert_called_with(
            device_id="tv",
            action=action,
            data=None,
        )

    def test_invalid_media(self, tools: CommandMeshTools) -> None:
        res = tools.media_control("tv", "fast_forward")
        assert res["success"] is False
        assert res["error"] == "invalid_parameter"


class TestToolDesktopActions:
    """Test desktop specific actions."""

    def test_press_key_valid(
        self,
        tools: CommandMeshTools,
        mock_client: MagicMock,
    ) -> None:
        tools.press_key("laptop", "ctrl,c")
        mock_client.execute_command.assert_called_with(
            device_id="laptop",
            action="press_keys",
            data="ctrl,c",
            desktop_only=True,
        )

    def test_press_key_empty(self, tools: CommandMeshTools) -> None:
        res = tools.press_key("laptop", "   ")
        assert res["success"] is False
        assert res["error"] == "invalid_parameter"

    def test_run_script_valid(
        self,
        tools: CommandMeshTools,
        mock_client: MagicMock,
    ) -> None:
        tools.run_script("laptop", "test.py")
        mock_client.execute_command.assert_called_with(
            device_id="laptop",
            action="run_script",
            data="test.py",
            desktop_only=True,
        )


class TestToolStandardActions:
    """Test text typing, URLs, home, lock, youtube."""

    def test_type_text(
        self,
        tools: CommandMeshTools,
        mock_client: MagicMock,
    ) -> None:
        tools.type_text("laptop", "hello world")
        mock_client.execute_command.assert_called_with(
            device_id="laptop",
            action="type_text",
            data="hello world",
        )

    def test_open_url_valid(
        self,
        tools: CommandMeshTools,
        mock_client: MagicMock,
    ) -> None:
        tools.open_url("laptop", "https://example.com")
        mock_client.execute_command.assert_called_with(
            device_id="laptop",
            action="open_url",
            data="https://example.com",
        )

    def test_open_url_invalid(self, tools: CommandMeshTools) -> None:
        res = tools.open_url("laptop", "ftp://invalid")
        assert res["success"] is False
        assert res["error"] == "invalid_parameter"

    def test_home(
        self,
        tools: CommandMeshTools,
        mock_client: MagicMock,
    ) -> None:
        tools.home("tv")
        mock_client.execute_command.assert_called_with(
            device_id="tv",
            action="home",
            data=None,
        )

    def test_lock_device(
        self,
        tools: CommandMeshTools,
        mock_client: MagicMock,
    ) -> None:
        tools.lock_device("laptop")
        mock_client.execute_command.assert_called_with(
            device_id="laptop",
            action="lock_pc",
            data=None,
        )

    def test_open_youtube(
        self,
        tools: CommandMeshTools,
        mock_client: MagicMock,
    ) -> None:
        tools.open_youtube("tv")
        mock_client.execute_command.assert_called_with(
            device_id="tv",
            action="open_youtube",
            data=None,
        )


class TestToolRegistryAndSchemas:
    """Test LLM tool list and schemas."""

    def test_get_tools_length(self, tools: CommandMeshTools) -> None:
        tool_list = tools.get_tools()
        assert len(tool_list) == 11
        for fn in tool_list:
            assert callable(fn)
            assert fn.__doc__ is not None

    def test_get_schemas(self, tools: CommandMeshTools) -> None:
        schemas = tools.get_schemas()
        assert len(schemas) == 11
        for s in schemas:
            assert s["type"] == "function"
            assert "name" in s["function"]
            assert "description" in s["function"]
            assert "parameters" in s["function"]

    def test_module_level_helpers(self, mock_client: MagicMock) -> None:
        tools = get_tools()
        schemas = get_tool_schemas()
        assert len(tools) == 11
        assert len(schemas) == 11

        from tool.tools import get_default_tools

        default_inst = get_default_tools()
        default_inst.client = mock_client

        from tool import (
            dpad,
            get_device_status,
            home,
            list_devices,
            lock_device,
            media_control,
            open_url,
            open_youtube,
            press_key,
            run_script,
            type_text,
        )

        assert list_devices()["success"] is True
        assert get_device_status("laptop")["success"] is True
        assert dpad("laptop", "up")["success"] is True
        assert media_control("tv", "vol_up")["success"] is True
        assert press_key("laptop", "ctrl,c")["success"] is True
        assert type_text("laptop", "hi")["success"] is True
        assert open_url("laptop", "https://test.com")["success"] is True
        assert home("tv")["success"] is True
        assert lock_device("laptop")["success"] is True
        assert open_youtube("tv")["success"] is True
        assert run_script("laptop", "test.py")["success"] is True

    def test_context_manager(
        self, tools: CommandMeshTools, mock_client: MagicMock
    ) -> None:
        with tools as t:
            assert t is tools
            mock_client.connect.assert_called_once()
        mock_client.disconnect.assert_called_once()


class TestMeshClientDirect:
    """Test MeshClient logic without mocks."""

    def test_offline_device_rejected(self) -> None:
        client = MeshClient(broker="mock.broker")
        client._connected = True
        client._devices["pc1"] = {"id": "pc1", "type": "pc", "online": False}

        res = client.execute_command("pc1", "home")
        assert res["success"] is False
        assert res["error"] == "device_offline"

    def test_desktop_only_on_tv_rejected(self) -> None:
        client = MeshClient(broker="mock.broker")
        client._connected = True
        client._devices["tv1"] = {"id": "tv1", "type": "tv", "online": True}

        res = client.execute_command("tv1", "press_keys", data="ctrl,c")
        assert res["success"] is False
        assert res["error"] == "invalid_command"

    def test_run_script_path_traversal_rejected(self) -> None:
        client = MeshClient(broker="mock.broker")
        client._connected = True
        client._devices["pc1"] = {"id": "pc1", "type": "pc", "online": True}

        res = client.execute_command("pc1", "run_script", data="../test.py")
        assert res["success"] is False
        assert res["error"] == "invalid_parameter"

    def test_desktop_node_directory_as_allowlist(self) -> None:
        from nodes.desktop.node import execute_action

        # Traversal attempts blocked
        ok, msg = execute_action("run_script", "../node.py")
        assert ok is False
        assert "Traversal detected" in msg

        ok, msg = execute_action("run_script", "../../main.py")
        assert ok is False
        assert "Traversal detected" in msg

        # Nonexistent script blocked
        ok, msg = execute_action("run_script", "nonexistent_script.py")
        assert ok is False
        assert "Script not found" in msg

        # Existing script inside scripts/ allowed
        ok, msg = execute_action("run_script", "test.bat")
        assert ok is True
        assert "launched" in msg

    def test_key_derivation(self) -> None:
        key = derive_key("test_passphrase")
        assert len(key) == 32
        assert isinstance(key, bytes)

    def test_on_connect_and_disconnect(self) -> None:
        client = MeshClient(broker="mock.broker", sender_id="mesh_agent")
        mock_mqtt = MagicMock()
        client._client = mock_mqtt

        client._on_connect(mock_mqtt, None, None, 0)
        assert client.is_connected is True
        mock_mqtt.subscribe.assert_any_call([("mesh/ack/mesh_agent", 1), ("mesh/presence/#", 1)])

        client._on_disconnect(mock_mqtt, None, None, 0)
        assert client.is_connected is False

    def test_on_message_discovery_and_ack(self) -> None:
        import json

        passphrase = "test_mesh_passphrase"
        client = MeshClient(broker="mock.broker", passphrase=passphrase, sender_id="mesh_agent")

        # Discovery message
        disc_msg = MagicMock()
        disc_msg.topic = "mesh/presence/node_1"
        disc_msg.payload = json.dumps(
            {
                "id": "node_1",
                "name": "Node One",
                "type": "tv",
                "status": "online",
            }
        ).encode("utf-8")
        client._on_message(MagicMock(), None, disc_msg)

        dev = client.get_device("node_1")
        assert dev is not None
        assert dev["online"] is True
        assert dev["type"] == "tv"

        # Outbox message
        ack_event = MagicMock()
        client._pending["req_99"] = ack_event

        ack_payload = create_ack_payload(
            sender_id="node_1",
            in_reply_to="req_99",
            status="success",
            output="done",
        )
        encrypted_ack = encrypt_payload(ack_payload, passphrase)

        out_msg = MagicMock()
        out_msg.topic = "mesh/ack/mesh_agent"
        out_msg.payload = encrypted_ack.encode("ascii")
        client._on_message(MagicMock(), None, out_msg)

        assert client._results.get("req_99")["status"] == "success"
        ack_event.set.assert_called_once()

    def test_execute_command_success(self) -> None:
        passphrase = "test_mesh_passphrase"
        client = MeshClient(
            broker="mock.broker",
            passphrase=passphrase,
            sender_id="agent_1",
            ack_timeout=0.5,
        )
        client._connected = True
        client._devices["pc1"] = {"id": "pc1", "type": "pc", "online": True}

        mock_mqtt = MagicMock()
        client._client = mock_mqtt

        # Mock publish triggering ACK
        def mock_pub(topic: str, b64_payload: str, qos: int = 1, retain: bool = False) -> None:
            decrypted = decrypt_payload(b64_payload, passphrase)
            assert decrypted is not None
            msg_id = decrypted["id"]
            ack_payload = create_ack_payload(
                sender_id="pc1",
                in_reply_to=msg_id,
                status="success",
                output="Key executed",
            )
            encrypted_ack = encrypt_payload(ack_payload, passphrase)
            ack_msg = MagicMock()
            ack_msg.topic = f"mesh/ack/{client.sender_id}"
            ack_msg.payload = encrypted_ack.encode("ascii")
            client._on_message(mock_mqtt, None, ack_msg)

        mock_mqtt.publish.side_effect = mock_pub

        res = client.execute_command("pc1", "home")
        assert res["success"] is True
        assert res["result"] == "Key executed"

    def test_execute_command_device_rejected(self) -> None:
        passphrase = "test_mesh_passphrase"
        client = MeshClient(
            broker="mock.broker",
            passphrase=passphrase,
            sender_id="agent_1",
            ack_timeout=0.5,
        )
        client._connected = True
        client._devices["pc1"] = {"id": "pc1", "type": "pc", "online": True}

        mock_mqtt = MagicMock()
        client._client = mock_mqtt

        def mock_pub(topic: str, b64_payload: str, qos: int = 1, retain: bool = False) -> None:
            decrypted = decrypt_payload(b64_payload, passphrase)
            assert decrypted is not None
            msg_id = decrypted["id"]
            ack_payload = create_ack_payload(
                sender_id="pc1",
                in_reply_to=msg_id,
                status="error",
                output="Error occurred",
            )
            encrypted_ack = encrypt_payload(ack_payload, passphrase)
            ack_msg = MagicMock()
            ack_msg.topic = f"mesh/ack/{client.sender_id}"
            ack_msg.payload = encrypted_ack.encode("ascii")
            client._on_message(mock_mqtt, None, ack_msg)

        mock_mqtt.publish.side_effect = mock_pub

        res = client.execute_command("pc1", "home")
        assert res["success"] is False
        assert res["error"] == "device_rejected"

    def test_execute_command_timeout(self) -> None:
        client = MeshClient(
            broker="mock.broker",
            passphrase="test_passphrase",
            ack_timeout=0.05,
        )
        client._connected = True
        client._devices["pc1"] = {"id": "pc1", "type": "pc", "online": True}
        client._client = MagicMock()

        res = client.execute_command("pc1", "home")
        assert res["success"] is False
        assert res["error"] == "device_timeout"
