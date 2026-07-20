class Freeact < Formula
  include Language::Python::Virtualenv

  desc "Undetectable browser automation CLI for AI agents via real browsers"
  homepage "https://github.com/xuviga/freeact"
  url "https://files.pythonhosted.org/packages/source/f/freeact-cli/freeact_cli-0.4.0.tar.gz"
  sha256 "REPLACE_WITH_ACTUAL_SHA256"
  license "MIT"

  depends_on "python@3.13"

  resource "playwright" do
    url "https://files.pythonhosted.org/packages/source/p/playwright/playwright-1.52.0-py3-none-any.whl"
  end

  def install
    virtualenv_install_with_resources

    system bin/"playwright", "install", "chromium"
  end

  test do
    system bin/"freeact", "--version"
  end
end
