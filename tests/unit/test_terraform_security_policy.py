from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_terraform_requires_acm_for_production_and_associates_waf() -> None:
    main = (ROOT / "infra/terraform/main.tf").read_text(encoding="utf-8")

    assert 'var.environment != "production" || var.certificate_arn != null' in main
    assert 'var.environment != "production" || var.enable_waf' in main
    assert "enable_waf" in main
    assert "aws_wafv2_web_acl" in main
    assert "aws_wafv2_web_acl_association" in main
