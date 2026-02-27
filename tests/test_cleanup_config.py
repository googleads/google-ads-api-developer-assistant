import sys
import os
import unittest
from unittest.mock import patch

# Add the project root to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
hooks_dir = os.path.join(project_root, ".gemini/hooks")
sys.path.append(hooks_dir)

import cleanup_config  # noqa: E402

class TestCleanupConfig(unittest.TestCase):

    @patch("os.path.exists")
    @patch("os.listdir")
    @patch("os.path.isfile")
    @patch("os.path.isdir")
    @patch("os.unlink")
    @patch("shutil.rmtree")
    def test_cleanup_success(self, mock_rmtree, mock_unlink, mock_isdir, mock_isfile, mock_listdir, mock_exists):
        # Setup mocks
        mock_exists.return_value = True
        mock_listdir.return_value = ["file1.txt", "dir1", ".gitkeep"]
        
        # Define side effects for isfile and isdir
        def is_file_side_effect(path):
            return "file1.txt" in path
        def is_dir_side_effect(path):
            return "dir1" in path
            
        mock_isfile.side_effect = is_file_side_effect
        mock_isdir.side_effect = is_dir_side_effect

        cleanup_config.cleanup()

        # Verify calls
        mock_unlink.assert_called_once()
        self.assertIn("file1.txt", mock_unlink.call_args[0][0])
        
        mock_rmtree.assert_called_once()
        self.assertIn("dir1", mock_rmtree.call_args[0][0])
        
        # Verify .gitkeep was NOT touched
        for call in mock_unlink.call_args_list:
            self.assertNotIn(".gitkeep", call[0][0])

    @patch("os.path.exists")
    def test_cleanup_no_config_dir(self, mock_exists):
        mock_exists.return_value = False
        with patch("sys.stderr") as mock_stderr:
            cleanup_config.cleanup()
            mock_stderr.write.assert_called()
            # Should not call listdir if it doesn't exist
            with patch("os.listdir") as mock_listdir:
                cleanup_config.cleanup()
                mock_listdir.assert_not_called()

if __name__ == "__main__":
    unittest.main()
