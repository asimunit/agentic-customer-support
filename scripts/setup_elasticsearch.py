#!/usr/bin/env python3
"""
Script to set up Elasticsearch for the Customer Support Resolver project.
This script helps with downloading, installing, and configuring Elasticsearch.
"""

import os
import sys
import subprocess
import platform
import zipfile
import tarfile
import requests
from pathlib import Path


def print_status(message):
    """Print status message"""
    print(f"✅ {message}")


def print_error(message):
    """Print error message"""
    print(f"❌ {message}")


def print_info(message):
    """Print info message"""
    print(f"ℹ️  {message}")


def check_java():
    """Check if Java is installed"""
    try:
        result = subprocess.run(['java', '-version'], capture_output=True,
                                text=True)
        if result.returncode == 0:
            print_status("Java is installed")
            return True
        else:
            print_error("Java is not installed")
            return False
    except FileNotFoundError:
        print_error("Java is not installed")
        return False


def download_elasticsearch():
    """Download Elasticsearch"""
    es_version = "8.11.0"
    system = platform.system().lower()

    if system == "windows":
        filename = f"elasticsearch-{es_version}-windows-x86_64.zip"
        url = f"https://artifacts.elastic.co/downloads/elasticsearch/{filename}"
    elif system == "darwin":  # macOS
        filename = f"elasticsearch-{es_version}-darwin-x86_64.tar.gz"
        url = f"https://artifacts.elastic.co/downloads/elasticsearch/{filename}"
    else:  # Linux
        filename = f"elasticsearch-{es_version}-linux-x86_64.tar.gz"
        url = f"https://artifacts.elastic.co/downloads/elasticsearch/{filename}"

    print_info(f"Downloading Elasticsearch {es_version} for {system}...")
    print_info(f"URL: {url}")

    # Create downloads directory
    downloads_dir = Path("downloads")
    downloads_dir.mkdir(exist_ok=True)

    filepath = downloads_dir / filename

    if filepath.exists():
        print_status(f"Elasticsearch already downloaded: {filepath}")
        return str(filepath)

    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\rDownload progress: {percent:.1f}%", end="",
                              flush=True)

        print()  # New line after progress
        print_status(f"Downloaded: {filepath}")
        return str(filepath)

    except Exception as e:
        print_error(f"Failed to download Elasticsearch: {e}")
        return None


def extract_elasticsearch(filepath):
    """Extract Elasticsearch archive"""
    print_info("Extracting Elasticsearch...")

    extract_dir = Path("elasticsearch")
    extract_dir.mkdir(exist_ok=True)

    try:
        if filepath.endswith('.zip'):
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
        else:
            with tarfile.open(filepath, 'r:gz') as tar_ref:
                tar_ref.extractall(extract_dir)

        print_status("Elasticsearch extracted successfully")

        # Find the actual elasticsearch directory
        es_dirs = [d for d in extract_dir.iterdir() if
                   d.is_dir() and d.name.startswith('elasticsearch')]
        if es_dirs:
            return str(es_dirs[0])
        else:
            print_error(
                "Could not find Elasticsearch directory after extraction")
            return None

    except Exception as e:
        print_error(f"Failed to extract Elasticsearch: {e}")
        return None


def configure_elasticsearch(es_dir):
    """Configure Elasticsearch for development"""
    print_info("Configuring Elasticsearch...")

    config_dir = Path(es_dir) / "config"
    config_file = config_dir / "elasticsearch.yml"

    # Development configuration
    dev_config = """
# Development configuration for Customer Support Resolver
cluster.name: customer-support-dev
node.name: node-1
path.data: data
path.logs: logs
network.host: localhost
http.port: 9200
discovery.type: single-node

# Security settings (disabled for development)
xpack.security.enabled: false
xpack.security.enrollment.enabled: false
xpack.security.http.ssl.enabled: false
xpack.security.transport.ssl.enabled: false

# ML settings
xpack.ml.enabled: false

# Monitoring
xpack.monitoring.collection.enabled: false
"""

    try:
        # Backup original config
        if config_file.exists():
            backup_file = config_file.with_suffix('.yml.backup')
            config_file.rename(backup_file)
            print_info(f"Backed up original config to {backup_file}")

        # Write development config
        with open(config_file, 'w') as f:
            f.write(dev_config)

        print_status("Elasticsearch configured for development")
        return True

    except Exception as e:
        print_error(f"Failed to configure Elasticsearch: {e}")
        return False


def create_start_script(es_dir):
    """Create script to start Elasticsearch"""
    print_info("Creating start script...")

    es_path = Path(es_dir)

    if platform.system().lower() == "windows":
        script_name = "start_elasticsearch.bat"
        script_content = f"""@echo off
echo Starting Elasticsearch...
cd /d "{es_path}"
bin\\elasticsearch.bat
"""
    else:
        script_name = "start_elasticsearch.sh"
        script_content = f"""#!/bin/bash
echo "Starting Elasticsearch..."
cd "{es_path}"
./bin/elasticsearch
"""

    try:
        with open(script_name, 'w') as f:
            f.write(script_content)

        if platform.system().lower() != "windows":
            os.chmod(script_name, 0o755)

        print_status(f"Created start script: {script_name}")
        return script_name

    except Exception as e:
        print_error(f"Failed to create start script: {e}")
        return None


def main():
    """Main setup function"""
    print("🔧 Elasticsearch Setup for Customer Support Resolver")
    print("=" * 50)

    # Check Java
    if not check_java():
        print_error("Java is required to run Elasticsearch")
        print_info("Please install Java 11 or later from https://openjdk.org/")
        sys.exit(1)

    # Download Elasticsearch
    filepath = download_elasticsearch()
    if not filepath:
        sys.exit(1)

    # Extract Elasticsearch
    es_dir = extract_elasticsearch(filepath)
    if not es_dir:
        sys.exit(1)

    # Configure Elasticsearch
    if not configure_elasticsearch(es_dir):
        sys.exit(1)

    # Create start script
    start_script = create_start_script(es_dir)
    if not start_script:
        sys.exit(1)

    print("\n" + "=" * 50)
    print_status("Elasticsearch setup complete!")
    print("\nNext steps:")
    print(f"1. Run the start script: ./{start_script}")
    print("2. Wait for Elasticsearch to start (usually 30-60 seconds)")
    print("3. Verify it's running: curl http://localhost:9200")
    print(
        "4. Run the knowledge base population script: python scripts/populate_knowledge_base.py")

    print("\nElasticsearch will be available at: http://localhost:9200")
    print("Use Ctrl+C to stop Elasticsearch when running")


if __name__ == "__main__":
    main()