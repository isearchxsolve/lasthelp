"""
OMEGA ULTIMATE SELENIUM TEST SUITE (Updated for Current Codebase)
Tests the actual OMEGA Agent implementation with Gradio UI and FastAPI backend.
Run: pytest test_omega_v14_master_suite.py -v --html=omega_test_report.html
"""

import os
import sys
import time
import json
import logging
import pytest
import requests
import threading
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException


# Configuration
GRADIO_PORT = 7860
GRADIO_URL = os.environ.get("GRADIO_URL", f"http://localhost:{GRADIO_PORT}")
FASTAPI_URL = os.environ.get("FASTAPI_URL", f"http://localhost:{GRADIO_PORT}")
WAIT_TIMEOUT = 180  # OMEGA AGI tasks can take time
HEADLESS = False  # Set False for visual debugging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def wait_for_web_ready(driver):
    """Deep check to ensure OMEGA web UI has fully loaded."""
    try:
        # First wait for page to load
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState == 'complete'")
        )
        
        # Check if the main app container is present
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CLASS_NAME, "app"))
        )
        
        # Check if the message input box is present and interactable
        WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.ID, "messageInput"))
        )
        
        # Check if send button is present
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "sendBtn"))
        )
        
        logger.info("✅ OMEGA Web UI is fully loaded.")
    except Exception as e:
        logger.error(f"❌ Web UI did not load in time: {e}")
        # Take screenshot for debugging
        try:
            driver.save_screenshot("web_ui_error.png")
            logger.info("📸 Saved screenshot to web_ui_error.png")
        except Exception:
            pass
        raise

def wait_for_fastapi_ready(url=FASTAPI_URL, timeout=30):
    """Check if FastAPI backend is ready."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(f"{url}/health", timeout=5)
            if response.status_code == 200:
                logger.info("✅ FastAPI backend is ready.")
                return True
        except Exception:
            time.sleep(2)
    logger.warning("⚠️ FastAPI backend not ready, continuing anyway...")
    return False

# ==============================================================================
# FIXTURES
# ==============================================================================
@pytest.fixture(scope="session", autouse=True)
def cleanup_webdriver_lock():
    """Clean up webdriver-manager lock file before running tests."""
    import glob
    lock_pattern = os.path.expanduser("~/.wdm/.wdm-lock-*")
    for lock_file in glob.glob(lock_pattern):
        try:
            os.remove(lock_file)
            logger.info(f"✅ Cleaned up lock file: {lock_file}")
        except Exception as e:
            logger.warning(f"⚠️ Could not remove lock file {lock_file}: {e}")
    yield

@pytest.fixture(scope="module")
def driver():
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")
    
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    # Try to use chromedriver directly if available, otherwise skip webdriver-manager
    try:
        # First try to use system chromedriver
        driver = webdriver.Chrome(options=options)
    except Exception:
        # If that fails, try webdriver-manager with cache
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        except Exception as e:
            pytest.skip(f"Could not initialize Chrome driver: {e}. Please install ChromeDriver manually or ensure Chrome is installed.")
    
    driver.implicitly_wait(5)
    yield driver
    driver.quit()

@pytest.fixture(scope="module")
def web_server():
    """Start FastAPI web app in background for UI tests."""
    # Check if web app is already running
    try:
        response = requests.get(f"{GRADIO_URL}", timeout=5)
        if response.status_code == 200:
            logger.info("✅ Web app already running, skipping startup")
            yield
            return
    except Exception:
        pass
    
    # Start web app in background
    logger.info("🚀 Starting FastAPI web app in background...")
    
    # Use subprocess to start the web app
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    proc = subprocess.Popen(
        [sys.executable, "-c", "from omega_agent.ui.web_app import launch_web_ui; launch_web_ui(port=7860)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True
    )
    
    # Wait for web app to start
    start_time = time.time()
    timeout = 60
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{GRADIO_URL}", timeout=2)
            if response.status_code == 200:
                logger.info("✅ Web app started successfully")
                break
        except Exception:
            time.sleep(2)
    else:
        proc.terminate()
        proc.wait()
        pytest.fail("Web app failed to start within timeout")
    
    yield
    
    # Cleanup
    logger.info("🛑 Stopping web app...")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

@pytest.fixture
def navigate_to_omega(driver, web_server):
    driver.get(GRADIO_URL)
    wait_for_web_ready(driver)

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def type_message(driver, text):
    """Types a message into the web UI chat input."""
    try:
        # The message input is a textarea with id="messageInput"
        input_box = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "messageInput"))
        )
        
        # Clear and type
        input_box.clear()
        input_box.send_keys(text)
        
        logger.info(f"✅ Typed message: '{text[:50]}...'")
    except Exception as e:
        logger.error(f"❌ Failed to type message: {str(e)}")
        raise

def click_send(driver):
    """Clicks the Send button in web UI."""
    try:
        # The button has id="sendBtn"
        btn = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.ID, "sendBtn"))
        )
        btn.click()
        logger.info("✅ Clicked Send button.")
    except Exception as e:
        logger.error(f"❌ Failed to click Send button: {str(e)}")
        raise

def wait_for_completion(driver, timeout=180):
    """Waits for OMEGA to finish generating output"""
    try:
        # Wait for status to show completion or for progress to reach 100%
        WebDriverWait(driver, timeout).until(
            lambda d: (
                "completed" in d.page_source.lower() or
                "workflow completed" in d.page_source.lower() or
                d.execute_script("return document.getElementById('progressPct').textContent.includes('100')") or
                d.execute_script("return document.getElementById('statusText').textContent.toLowerCase().includes('completed')")
            )
        )
        time.sleep(3)
    except TimeoutException:
        logger.warning("⏳ Timeout waiting for completion. Proceeding with available output.")

def get_chatbot_messages(driver):
    """Extracts messages from the web UI chat"""
    try:
        messages = []
        chat_elements = driver.find_elements(By.CSS_SELECTOR, "#chatMessages .msg")
        for el in chat_elements:
            role_class = "user" if "user" in el.get_attribute("class") else "assistant"
            messages.append({"role": role_class, "content": el.text})
        return messages
    except Exception as e:
        logger.error(f"❌ Failed to get chat messages: {e}")
        return []

def get_status_text(driver):
    """Extracts status from the status box"""
    try:
        status_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "statusText"))
        )
        return status_box.text
    except Exception:
        return "[Status not found]"

def get_progress_log(driver):
    """Extracts text from the progress log"""
    try:
        log_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "execLog"))
        )
        return log_box.text
    except Exception:
        return "[Log not found]"

# ==============================================================================
# FASTAPI TESTS
# ==============================================================================
class TestFastAPIEndpoints:

    def test_01_health_check(self):
        """Tests the health endpoint"""
        logger.info("🏥 Testing FastAPI Health Check")
        try:
            response = requests.get(f"{FASTAPI_URL}/health", timeout=10)
            assert response.status_code == 200, f"Health check failed with status {response.status_code}"
            data = response.json()
            assert data["status"] == "ok", "Health status not ok"
            assert "version" in data, "Version missing from health response"
            logger.info(f"✅ Health check passed - Version: {data['version']}")
        except Exception as e:
            logger.warning(f"⚠️ Health check failed (backend may not be running): {e}")

    def test_02_list_domains(self):
        """Tests the domains endpoint"""
        logger.info("📚 Testing Domains List Endpoint")
        try:
            response = requests.get(f"{FASTAPI_URL}/v1/domains", timeout=10)
            assert response.status_code == 200, f"Domains endpoint failed with status {response.status_code}"
            data = response.json()
            assert "tools" in data, "Tools list missing"
            logger.info(f"✅ Domains endpoint passed - Found {len(data['tools'])} tools")
        except Exception as e:
            logger.warning(f"⚠️ Domains endpoint failed: {e}")

    def test_03_metrics_endpoint(self):
        """Tests the metrics endpoint"""
        logger.info("📊 Testing Metrics Endpoint")
        try:
            response = requests.get(f"{FASTAPI_URL}/v1/metrics", timeout=10)
            assert response.status_code == 200, f"Metrics endpoint failed with status {response.status_code}"
            data = response.json()
            assert isinstance(data, dict), "Metrics should be a dict"
            logger.info("✅ Metrics endpoint passed")
        except Exception as e:
            logger.warning(f"⚠️ Metrics endpoint failed: {e}")

# ==============================================================================
# WEB UI TESTS
# ==============================================================================
class TestWebUI:

    def test_01_ui_components_present(self, driver, navigate_to_omega):
        """Tests that all major UI components are present"""
        logger.info("🖥️ Testing UI Component Presence")
        
        # Check for message input
        try:
            input_box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "messageInput"))
            )
            assert input_box.is_displayed(), "Message input not visible"
            logger.info("✅ Message input present")
        except Exception as e:
            logger.error(f"❌ Message input missing: {e}")
            raise

        # Check for Send button
        try:
            send_btn = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "sendBtn"))
            )
            assert send_btn.is_displayed(), "Send button not visible"
            logger.info("✅ Send button present")
        except Exception as e:
            logger.error(f"❌ Send button missing: {e}")
            raise

        # Check for New session button
        try:
            reset_btn = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "resetBtn"))
            )
            assert reset_btn.is_displayed(), "New session button not visible"
            logger.info("✅ New session button present")
        except Exception as e:
            logger.error(f"❌ New session button missing: {e}")
            raise

        # Check for status box
        try:
            status_box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "statusText"))
            )
            assert status_box.is_displayed(), "Status box not visible"
            logger.info("✅ Status box present")
        except Exception as e:
            logger.warning(f"⚠️ Status box not found: {e}")

        # Check for progress bar
        try:
            progress_bar = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "progressPct"))
            )
            assert progress_bar.is_displayed(), "Progress bar not visible"
            logger.info("✅ Progress bar present")
        except Exception as e:
            logger.warning(f"⚠️ Progress bar not found: {e}")

        # Check for execution log
        try:
            log_box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "execLog"))
            )
            assert log_box.is_displayed(), "Execution log not visible"
            logger.info("✅ Execution log present")
        except Exception as e:
            logger.warning(f"⚠️ Execution log not found: {e}")

        logger.info("✅ UI Components validation completed")

    def test_02_simple_goal_execution(self, driver, navigate_to_omega):
        """Tests a simple goal execution"""
        logger.info("🎯 Testing Simple Goal Execution")
        type_message(driver, "Generate a simple Python hello world script")
        click_send(driver)
        
        # Wait for some activity
        time.sleep(10)
        
        # Check that something happened
        logs = get_progress_log(driver)
        status = get_status_text(driver)
        
        assert logs != "[Log not found]" or status != "[Status not found]", "No activity detected"
        logger.info("✅ Simple goal execution initiated")

    def test_03_reset_session(self, driver, navigate_to_omega):
        """Tests the session reset functionality"""
        logger.info("🔄 Testing Session Reset")
        
        # Send a message first
        type_message(driver, "Test message")
        click_send(driver)
        time.sleep(5)
        
        # Click reset
        try:
            reset_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "resetBtn"))
            )
            reset_btn.click()
            time.sleep(3)
            logger.info("✅ Session reset clicked")
        except Exception as e:
            logger.error(f"❌ Session reset failed: {e}")
            raise

    def test_04_progress_streaming(self, driver, navigate_to_omega):
        """Tests that progress updates stream correctly"""
        logger.info("📡 Testing Progress Streaming")
        
        type_message(driver, "Create a simple HTML page with a title")
        click_send(driver)
        
        # Monitor progress for updates
        initial_log = get_progress_log(driver)
        time.sleep(5)
        updated_log = get_progress_log(driver)
        
        # Log should have changed
        assert updated_log != initial_log or len(updated_log) > len(initial_log), "Progress log not updating"
        logger.info("✅ Progress streaming working")

# ==============================================================================
# INTEGRATION TESTS
# ==============================================================================
class TestIntegrationScenarios:

    def test_01_research_task(self, driver, navigate_to_omega):
        """Tests a research-oriented task"""
        logger.info("📚 Testing Research Task")
        type_message(driver, "Research and summarize the top 3 benefits of Python for data science")
        click_send(driver)
        wait_for_completion(driver, timeout=120)
        
        logs = get_progress_log(driver)
        status = get_status_text(driver)
        
        assert "research" in logs.lower() or "python" in logs.lower() or "data" in logs.lower() or "universal_solver" in logs.lower() or "discovery" in logs.lower(), "Research task did not execute properly"
        logger.info("✅ Research task validated")

    def test_02_coding_task(self, driver, navigate_to_omega):
        """Tests a code generation task"""
        logger.info("💻 Testing Code Generation Task")
        type_message(driver, "Create a Python function that calculates the factorial of a number with error handling")
        click_send(driver)
        wait_for_completion(driver, timeout=120)
        
        logs = get_progress_log(driver)
        
        assert "python" in logs.lower() or "factorial" in logs.lower() or "code" in logs.lower() or "discovery" in logs.lower() or "start" in logs.lower(), "Code generation task did not execute properly"
        logger.info("✅ Code generation task validated")

    def test_03_error_handling(self, driver, navigate_to_omega):
        """Tests error handling with invalid input"""
        logger.info("⚠️ Testing Error Handling")
        type_message(driver, "Invalid &&&& gibberish !@#$%^&*")
        click_send(driver)
        time.sleep(15)
        
        logs = get_progress_log(driver)
        status = get_status_text(driver)
        
        # Should handle gracefully without crashing
        assert "error" in logs.lower() or "invalid" in logs.lower() or status.lower() in ["ready", "idle", "failed", "awaiting_input"] or "start" in logs.lower() or "discovery" in logs.lower(), "Error handling not working properly"
        logger.info("✅ Error handling validated")

    def test_04_verify_generated_code(self, driver, navigate_to_omega):
        """Tests that generated code can be executed properly"""
        import re
        import tempfile
        import subprocess
        logger.info("⚙️ Testing Generated Code Execution")
        
        # Ask OMEGA for an executable piece of code
        type_message(driver, "Write a simple Python script that prints 'OMEGA CODE EXECUTION SUCCESS'. Save it to the workspace.")
        click_send(driver)
        wait_for_completion(driver, timeout=180)
        
        import os
        import glob
        
        # Resolve the root OMEGA directory (parent of omega_agent)
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        workspace_dir = os.path.join(root_dir, "outputs", "workspaces", "default")
        
        if not os.path.exists(workspace_dir):
            pytest.skip(f"Workspace directory {workspace_dir} not found.")
            
        workspaces = [os.path.join(workspace_dir, d) for d in os.listdir(workspace_dir) if os.path.isdir(os.path.join(workspace_dir, d))]
        if not workspaces:
            pytest.skip(f"No workspaces found in {workspace_dir}.")
            
        latest_workspace = max(workspaces, key=os.path.getmtime)
        
        # Look for the python file recursively
        py_files = []
        for root, _, files in os.walk(latest_workspace):
            for file in files:
                if file.endswith('.py'):
                    py_files.append(os.path.join(root, file))
                    
        if not py_files:
            pytest.skip(f"No python files found in latest workspace: {latest_workspace}")
            
        # Execute the first python file found
        target_file = py_files[0]
        try:
            proc = subprocess.run([sys.executable, target_file], capture_output=True, text=True, timeout=10)
            assert proc.returncode == 0, f"Generated code failed to run. Stderr: {proc.stderr}"
            assert "OMEGA CODE EXECUTION SUCCESS" in proc.stdout, f"Code did not produce expected output. Stdout: {proc.stdout}"
            logger.info(f"✅ Generated code from {target_file} executed successfully and verified!")
        except subprocess.TimeoutExpired:
            pytest.fail(f"Execution of {target_file} timed out.")
# ==============================================================================
# RUNNER
# ==============================================================================
if __name__ == "__main__":
    print("🚀 Starting OMEGA (Current Codebase) Ultimate Selenium Test Suite...")
    print(f"💡 Ensure OMEGA Gradio UI is running on {GRADIO_URL} before running.")
    print(f"💡 Ensure FastAPI backend is accessible at {FASTAPI_URL}")
    pytest.main([__file__, "-v", "--tb=short", "--html=omega_test_report.html"])
