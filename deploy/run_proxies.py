"""
Launch both LiteLLM proxy and the auth passthrough proxy
"""
import os
import signal
import subprocess
import sys
import time


# noinspection D
def run_proxies():
    """Start both litellm proxy and auth proxy"""
    processes = []

    try:
        # Get DATABASE_URL from environment
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            print("ERROR: DATABASE_URL environment variable not set")
            sys.exit(1)

        # Get virtual key
        virtual_key = os.environ.get('LITELLM_VIRTUAL_KEY')
        if not virtual_key:
            print("WARNING: LITELLM_VIRTUAL_KEY environment variable not set")

        print("Starting LiteLLM Proxy on port 4000...")
        litellm_process = subprocess.Popen(
            ["litellm", "--config", "config/config.yaml", "--detailed_debug", "--save"],
            env=os.environ.copy(),
        )
        processes.append(("LiteLLM Proxy", litellm_process))

        # Wait a bit for litellm to start
        time.sleep(5)

        # Check if litellm started successfully
        if litellm_process.poll() is not None:
            print(f"ERROR: LiteLLM Proxy failed to start (exit code: {litellm_process.returncode})")
            print("Please check if port 4000 is already in use or if there are configuration issues.")
            sys.exit(1)

        print("Starting Auth Passthrough Proxy on port 8764...")
        auth_proxy_process = subprocess.Popen(
            [sys.executable, "src/proxy/litellm_proxy_with_memory.py"],
            env=os.environ.copy(),
        )
        processes.append(("Auth Proxy", auth_proxy_process))

        print("\n" + "="*60)
        print("Both proxies started successfully!")
        print("="*60)
        print(f"LiteLLM Proxy:     http://localhost:4000")
        print(f"Auth Proxy:        http://localhost:8764")
        print(f"Master Key:        sk-1234")
        print(f"Virtual Key:       {virtual_key or 'NOT SET'}")
        print("="*60)
        print("\nPress Ctrl+C to stop both proxies\n")

        # Monitor both processes
        while True:
            for name, process in processes:
                if process.poll() is not None:
                    print(f"\n{name} (PID {process.pid}) exited with code {process.returncode}")
                    raise KeyboardInterrupt
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nShutting down proxies...")
        for name, process in processes:
            if process.poll() is None:
                print(f"Stopping {name} (PID {process.pid})...")
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(f"Force killing {name} (PID {process.pid})...")
                    process.kill()
            else:
                pass

        print("All proxies stopped.")
        sys.exit(0)


if __name__ == "__main__":
    run_proxies()
