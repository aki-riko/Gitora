import unittest

from PySide6.QtCore import QCoreApplication

from app_qml.backend.startup_handoff_bridge import StartupHandoffBridge


class _Controller:
    _handoff_done = False


class StartupHandoffBridgeTest(unittest.TestCase):
    def test_emits_only_after_controller_handoff(self) -> None:
        QCoreApplication.instance() or QCoreApplication([])
        controller = _Controller()
        bridge = StartupHandoffBridge(controller)
        emitted = []
        bridge.startupHandoffReady.connect(lambda: emitted.append(True))

        bridge._poll()
        self.assertEqual(emitted, [])
        self.assertTrue(bridge._poll_timer.isActive())

        controller._handoff_done = True
        bridge._poll()
        self.assertEqual(emitted, [True])
        self.assertFalse(bridge._poll_timer.isActive())


if __name__ == "__main__":
    unittest.main()
