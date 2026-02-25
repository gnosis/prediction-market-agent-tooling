# Install Dependencies

Before getting started, ensure you have the following tools installed:

- **Python >= 3.10**
- **Poetry** (for dependency management)
- **Git** (for version control)
- **GCP CLI** (optional, for deploying and monitoring agents)


## Installation Steps

### **1. Install Python >= 3.10**

#### **Check Python Version:**
```bash
python3 --version
```

#### **Install Python:**

- **On Ubuntu/Debian:**
  ```bash
  sudo apt update
  sudo apt install -y software-properties-common
  sudo add-apt-repository ppa:deadsnakes/ppa
  sudo apt update
  sudo apt install -y python3.10 python3.10-venv python3.10-dev
  ```

- **On macOS (with Homebrew):**
  ```bash
  brew install python@3.10
  ```

- **On Windows:**
  1. Download Python from the [official Python website](https://www.python.org/downloads/).
  2. Run the installer and ensure "Add Python to PATH" is checked.

#### **Verify Installation:**
```bash
python3 --version
```

---

### **2. Install Poetry (Dependency Management)**

#### **Check if Poetry is Already Installed:**
```bash
poetry --version
```

#### **Install Poetry:**
- Run the following command:
  ```bash
  curl -sSL https://install.python-poetry.org | python3 -
  ```

#### **Add Poetry to PATH (if not already added):**
- **Linux/macOS:**
  ```bash
  export PATH="$HOME/.local/bin:$PATH"
  ```
  Add the above line to your shell configuration file (`~/.bashrc`, `~/.zshrc`, or similar).

- **Windows:**
  Poetry is added to PATH during installation, but you may need to restart your terminal.

#### **Verify Installation:**
```bash
poetry --version
```

---

### **3. Install Git (Version Control)**

#### **Check if Git is Already Installed:**
```bash
git --version
```

#### **Install Git:**
- **On Ubuntu/Debian:**
  ```bash
  sudo apt update
  sudo apt install -y git
  ```

- **On macOS (with Homebrew):**
  ```bash
  brew install git
  ```

- **On Windows:**
  1. Download Git from the [official Git website](https://git-scm.com/).
  2. Run the installer and follow the setup wizard.

#### **Verify Installation:**
```bash
git --version
```

---

### **4. Install GCP CLI (Google Cloud CLI)** *(Optional)*

#### **Check if GCP CLI is Already Installed:**
```bash
gcloud --version
```

#### **Install GCP CLI:**

- **On Ubuntu/Debian:**
  ```bash
  sudo apt update
  sudo apt install -y apt-transport-https ca-certificates gnupg
  echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
  sudo apt install -y google-cloud-sdk
  ```

- **On macOS (with Homebrew):**
  ```bash
  brew install --cask google-cloud-sdk
  ```

- **On Windows:**
  1. Download the installer from the [GCP CLI website](https://cloud.google.com/sdk/docs/install).
  2. Run the installer and follow the setup wizard.

#### **Initialize GCP CLI:**
After installation, run the following to set up the CLI:
```bash
gcloud init
```

#### **Verify Installation:**
```bash
gcloud --version
```

---

By completing these steps, you'll have Python, Poetry, Git, and optionally GCP CLI installed and ready to use.



