#!/bin/bash
# Verify the project setup is correct

set -e

echo "🔍 Verifying assistant package setup..."
echo ""

# Check Python version
echo "✓ Checking Python version..."
python3 --version 2>/dev/null | grep -E "3\.(13|14|15)" || {
    echo "❌ Python 3.13+ required"
    exit 1
}

# Check if in project root
echo "✓ Checking project structure..."
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Not in project root (pyproject.toml not found)"
    exit 1
fi

# Check src layout
if [ ! -d "src/assistant" ]; then
    echo "❌ src/assistant directory not found"
    exit 1
fi

# Check documentation
if [ ! -d "docs/adr" ] || [ ! -d "docs/agents" ] || [ ! -d "docs/modules" ] || [ ! -d "docs/architecture" ]; then
    echo "❌ Documentation directories incomplete"
    exit 1
fi

# Check configuration files
if [ ! -f ".cursorrules" ] || [ ! -f ".claude/code_style.md" ]; then
    echo "❌ AI configuration files missing"
    exit 1
fi

# Check test directory
if [ ! -d "tests" ]; then
    echo "❌ tests directory not found"
    exit 1
fi

echo "✓ Project structure verified"
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "⚠️  Virtual environment not found (.venv)"
    echo "   Run: uv venv"
    echo ""
fi

# Check if package is installed
if [ -d ".venv" ]; then
    echo "✓ Checking package installation..."
    source .venv/bin/activate 2>/dev/null || true
    if python3 -c "import assistant" 2>/dev/null; then
        echo "✓ Package is installed"
        python3 -c "import assistant; print(f'   Version: {assistant.__version__}')"
    else
        echo "⚠️  Package not installed"
        echo "   Run: uv pip install -e \".[dev]\""
    fi
fi

echo ""
echo "📊 File count:"
echo "   Source files: $(find src -name '*.py' | wc -l | tr -d ' ')"
echo "   Test files: $(find tests -name '*.py' | wc -l | tr -d ' ')"
echo "   Documentation files: $(find docs -name '*.md' | wc -l | tr -d ' ')"
echo ""

echo "✅ Setup verification complete!"
echo ""
echo "Next steps:"
echo "  1. Create virtual environment: uv venv"
echo "  2. Activate it: source .venv/bin/activate"
echo "  3. Install package: uv pip install -e \".[dev]\""
echo "  4. Run tests: pytest"
echo "  5. Type check: mypy src/"
echo ""
echo "📚 Documentation: docs/agents/working-with-this-codebase.md"
