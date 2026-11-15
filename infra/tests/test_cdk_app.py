"""Offline CDK synthesis and security assertions; never contacts AWS."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aws_cdk import ArnFormat, assertions
from infra.app import create_app
from infra.config import EnvConfig

DEV = EnvConfig(env_name="dev")
PROD = EnvConfig(env_name="prod", account="111111111111", region="ap-southeast-1")


def _template(config: EnvConfig = DEV) -> assertions.Template:
    _app, stack = create_app(config)
    return assertions.Template.from_stack(stack)


@pytest.mark.parametrize("config", [DEV, PROD])
def test_synthesis_needs_no_context_and_preserves_two_azs(config: EnvConfig) -> None:
    app, stack = create_app(config)
    assembly = app.synth()
    manifest = json.loads((Path(assembly.directory) / "manifest.json").read_text())
    assert not manifest.get("missing", [])
    if config.account:
        assert stack.account == config.account
        assert stack.region == config.region
    template = assertions.Template.from_stack(stack)
    subnets = template.find_resources("AWS::EC2::Subnet")
    assert len(subnets) == 6
    assert [subnet["Properties"]["AvailabilityZone"] for subnet in subnets.values()] == [
        {"Fn::Select": [index, {"Fn::GetAZs": ""}]} for index in (0, 1, 0, 1, 0, 1)
    ]


@pytest.mark.parametrize("config", [DEV, PROD])
def test_artifact_key_allows_logs_only_for_application_log_groups(config: EnvConfig) -> None:
    _app, stack = create_app(config)
    template = assertions.Template.from_stack(stack)
    body = template.to_json()
    groups = template.find_resources("AWS::Logs::LogGroup")
    key_refs = [group["Properties"]["KmsKeyId"]["Fn::GetAtt"][0] for group in groups.values()]
    assert len(set(key_refs)) == 1
    key = body["Resources"][key_refs[0]]
    statements = key["Properties"]["KeyPolicy"]["Statement"]
    log_statements = [s for s in statements if s.get("Sid") == "AllowApplicationLogs"]
    assert len(log_statements) == 1
    statement = log_statements[0]
    assert statement["Effect"] == "Allow"
    assert set(statement["Action"]) == {
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:Describe*",
    }
    assert statement["Resource"] == "*"
    assert statement["Principal"] == {
        "Service": stack.resolve(f"logs.{stack.region}.{stack.url_suffix}")
    }
    expected_arns = [
        stack.resolve(
            stack.format_arn(
                service="logs",
                resource="log-group",
                resource_name=group["Properties"]["LogGroupName"],
                arn_format=ArnFormat.COLON_RESOURCE_NAME,
            )
        )
        for group in groups.values()
    ]
    assert statement["Condition"] == {
        "ArnEquals": {"kms:EncryptionContext:aws:logs:arn": expected_arns}
    }


def test_stack_contains_target_architecture_resources() -> None:
    template = _template()
    template.resource_count_is("AWS::EC2::VPC", 1)
    template.resource_count_is("AWS::ElasticLoadBalancingV2::LoadBalancer", 1)
    template.resource_count_is("AWS::ElasticLoadBalancingV2::Listener", 2)
    template.resource_count_is("AWS::ElasticLoadBalancingV2::TargetGroup", 2)
    template.resource_count_is("AWS::ECS::Cluster", 1)
    template.resource_count_is("AWS::ECS::Service", 2)
    template.resource_count_is("AWS::ECS::TaskDefinition", 3)
    template.resource_count_is("AWS::ECR::Repository", 3)
    template.resource_count_is("AWS::RDS::DBInstance", 1)
    template.resource_count_is("AWS::S3::Bucket", 1)
    template.resource_count_is("AWS::Cognito::UserPool", 1)
    template.resource_count_is("AWS::Cognito::UserPoolClient", 1)
    template.resource_count_is("AWS::Cognito::UserPoolGroup", 3)
    template.resource_count_is("AWS::SecretsManager::Secret", 2)
    template.resource_count_is("AWS::CloudWatch::Alarm", 5)
    template.resource_count_is("AWS::Logs::LogGroup", 3)


def test_vpc_has_two_az_subnet_tiers_and_isolated_database_subnets() -> None:
    template = _template()
    template.has_resource_properties(
        "AWS::EC2::VPC",
        {"EnableDnsHostnames": True, "EnableDnsSupport": True},
    )
    template.resource_count_is("AWS::EC2::Subnet", 6)
    template.resource_count_is("AWS::EC2::NatGateway", 1)
    template.has_resource_properties(
        "AWS::EC2::Subnet",
        {"MapPublicIpOnLaunch": True},
    )
    template.has_resource_properties(
        "AWS::EC2::Subnet",
        {
            "Tags": assertions.Match.array_with(
                [assertions.Match.object_like({"Value": "isolated-data"})]
            )
        },
    )


def test_public_alb_uses_tls_redirect_and_private_targets() -> None:
    template = _template()
    template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        {"Scheme": "internet-facing", "Type": "application"},
    )
    template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::Listener",
        {
            "Port": 443,
            "Protocol": "HTTPS",
            "Certificates": assertions.Match.array_with(
                [assertions.Match.object_like({"CertificateArn": assertions.Match.any_value()})]
            ),
        },
    )
    template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::ListenerRule",
        {
            "Conditions": assertions.Match.array_with(
                [
                    assertions.Match.object_like(
                        {
                            "Field": "path-pattern",
                            "PathPatternConfig": {
                                "Values": ["/api/*"],
                            },
                        }
                    )
                ]
            )
        },
    )
    template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::Listener",
        {
            "Port": 80,
            "DefaultActions": assertions.Match.array_with(
                [assertions.Match.object_like({"Type": "redirect"})]
            ),
        },
    )
    for properties in template.find_resources("AWS::ECS::Service").values():
        assert (
            properties["Properties"]["NetworkConfiguration"]["AwsvpcConfiguration"][
                "AssignPublicIp"
            ]
            == "DISABLED"
        )


def test_rds_is_private_encrypted_and_dev_backup_is_configured() -> None:
    template = _template()
    template.has_resource_properties(
        "AWS::RDS::DBInstance",
        {
            "Engine": "postgres",
            "PubliclyAccessible": False,
            "StorageEncrypted": True,
            "BackupRetentionPeriod": 3,
            "DeletionProtection": False,
        },
    )


def test_s3_is_versioned_encrypted_private_and_deletable_in_dev() -> None:
    template = _template()
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "VersioningConfiguration": {"Status": "Enabled"},
            "BucketEncryption": assertions.Match.object_like(
                {"ServerSideEncryptionConfiguration": assertions.Match.any_value()}
            ),
        },
    )
    bucket = next(iter(template.find_resources("AWS::S3::Bucket").values()))
    public_access = bucket["Properties"]["PublicAccessBlockConfiguration"]
    assert public_access == {
        "BlockPublicAcls": True,
        "BlockPublicPolicy": True,
        "IgnorePublicAcls": True,
        "RestrictPublicBuckets": True,
    }
    assert bucket["DeletionPolicy"] == "Delete"


def test_ecr_repositories_are_immutable_and_scanned() -> None:
    template = _template()
    repos = template.find_resources("AWS::ECR::Repository")
    assert len(repos) == 3
    for repository in repos.values():
        properties = repository["Properties"]
        assert properties["ImageTagMutability"] == "IMMUTABLE"
        assert properties["ImageScanningConfiguration"]["ScanOnPush"] is True


def test_task_roles_are_separate_and_data_permissions_are_prefix_scoped() -> None:
    template = _template()
    roles = template.find_resources("AWS::IAM::Role")
    by_description = {
        role["Properties"].get("Description"): logical_id for logical_id, role in roles.items()
    }
    frontend_role = by_description["Frontend has no direct AWS data or secret permissions."]
    api_role = by_description["API task role may read processed artifacts only."]
    worker_role = by_description[
        "Ingestion task role accesses source and processed artifact prefixes."
    ]
    assert len({frontend_role, api_role, worker_role}) == 3

    policies = template.find_resources("AWS::IAM::Policy")

    def statements_for(role_id: str) -> list[dict[str, object]]:
        return [
            statement
            for policy in policies.values()
            if any(role.get("Ref") == role_id for role in policy["Properties"]["Roles"])
            for statement in policy["Properties"]["PolicyDocument"]["Statement"]
        ]

    assert statements_for(frontend_role) == []
    api_statements = statements_for(api_role)
    worker_statements = statements_for(worker_role)
    assert api_statements and worker_statements
    api_resources = str([statement["Resource"] for statement in api_statements])
    worker_resources = str([statement["Resource"] for statement in worker_statements])
    assert "/processed/*" in api_resources
    assert "/source/*" in worker_resources
    assert "/processed/*" in worker_resources
    assert "secretsmanager:" not in str([statement["Action"] for statement in api_statements])
    assert all(statement["Resource"] != "*" for statement in api_statements + worker_statements)


def test_cognito_groups_are_application_roles_and_client_has_no_secret() -> None:
    template = _template()
    groups = template.find_resources("AWS::Cognito::UserPoolGroup")
    assert {group["Properties"]["GroupName"] for group in groups.values()} == {
        "student",
        "adviser",
        "admin",
    }
    template.has_resource_properties(
        "AWS::Cognito::UserPoolClient",
        {"GenerateSecret": False, "EnableTokenRevocation": True},
    )


def test_prod_retains_data_and_enables_rds_deletion_protection_and_multi_az() -> None:
    template = _template(PROD)
    template.has_resource_properties(
        "AWS::RDS::DBInstance",
        {
            "PubliclyAccessible": False,
            "DeletionProtection": True,
            "MultiAZ": True,
            "BackupRetentionPeriod": 14,
        },
    )
    database = next(iter(template.find_resources("AWS::RDS::DBInstance").values()))
    assert database["DeletionPolicy"] == "Retain"
    bucket = next(iter(template.find_resources("AWS::S3::Bucket").values()))
    assert bucket["DeletionPolicy"] == "Retain"
    assert bucket["UpdateReplacePolicy"] == "Retain"
    template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        {
            "LoadBalancerAttributes": assertions.Match.array_with(
                [
                    assertions.Match.object_like(
                        {"Key": "deletion_protection.enabled", "Value": "true"}
                    )
                ]
            )
        },
    )
    template.has_resource_properties(
        "AWS::Cognito::UserPool",
        {"DeletionProtection": "ACTIVE"},
    )
    template.resource_count_is("AWS::EC2::NatGateway", 2)


def test_required_external_certificate_and_immutable_image_tag_are_explicit() -> None:
    template = _template()
    body = template.to_json()
    parameters = body.get("Parameters", {})
    assert "AcmCertificateArn" in parameters
    assert "ImmutableImageTag" not in parameters
    task_definitions = template.find_resources("AWS::ECS::TaskDefinition").values()
    images = [
        container["Image"]
        for task in task_definitions
        for container in task["Properties"]["ContainerDefinitions"]
    ]
    assert len(images) == 3
    assert all("m6-synth-placeholder" in str(image) for image in images)
    assert "Outputs" in body
    assert "AWS::SecretsManager::Secret" not in str(body["Outputs"])


def test_config_rejects_latest_image_tag_and_incomplete_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CDK_ENV", "dev")
    monkeypatch.delenv("CDK_DEFAULT_ACCOUNT", raising=False)
    monkeypatch.delenv("AWS_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CDK_DEFAULT_REGION", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.setenv("CDK_IMAGE_TAG", "latest")
    with pytest.raises(ValueError, match="immutable release tag"):
        EnvConfig.from_env()
