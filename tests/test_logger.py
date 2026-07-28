import logging
import unittest

from app.common.logger import _ExcludePrismConsoleDuplicates


class LoggerFilterTest(unittest.TestCase):
    def test_prism_console_duplicate_is_filtered_but_app_warning_remains(self) -> None:
        console_filter = _ExcludePrismConsoleDuplicates()

        self.assertFalse(console_filter.filter(logging.LogRecord(
            "PrismQML", logging.WARNING, __file__, 1, "qml warning", (), None
        )))
        self.assertTrue(console_filter.filter(logging.LogRecord(
            "GitBridge", logging.WARNING, __file__, 1, "git warning", (), None
        )))


if __name__ == "__main__":
    unittest.main()
