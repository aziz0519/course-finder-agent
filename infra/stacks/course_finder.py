"""Synthesizable AWS target architecture for course-finder-agent.

This stack defines infrastructure only. Container publishing, runtime S3/RDS
adapters, Cognito token verification, and deployment are separate release tasks.
"""

from __future__ import annotations

from aws_cdk import (
    ArnFormat,
    CfnOutput,
    CfnParameter,
    Duration,
    Environment,
    Fn,
    RemovalPolicy,
    Stack,
    Tags,
)
from aws_cdk import (
    aws_certificatemanager as acm,
)
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
)
from aws_cdk import (
    aws_cognito as cognito,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_ecr as ecr,
)
from aws_cdk import (
    aws_ecs as ecs,
)
from aws_cdk import (
    aws_elasticloadbalancingv2 as elbv2,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_kms as kms,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_rds as rds,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

from infra.config import EnvConfig


class CourseFinderStack(Stack):
    """Single deployable stack with an explicit environment data boundary."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: EnvConfig,
        env: Environment | None = None,
        description: str | None = None,
    ) -> None:
        super().__init__(scope, construct_id, env=env, description=description)
        self.config = config
        self._tag_resources()
        self._create_network()
        self._create_storage_and_database()
        self._create_identity()
        self._create_repositories_and_cluster()
        self._create_application_services()
        self._create_observability()
        self._create_outputs()

    @property
    def availability_zones(self) -> list[str]:
        """Resolve two AZs at deployment without account/Region context lookups."""
        return [Fn.select(index, Fn.get_azs()) for index in range(2)]

    def _tag_resources(self) -> None:
        Tags.of(self).add("Application", "course-finder-agent")
        Tags.of(self).add("Environment", self.config.env_name)
        Tags.of(self).add("Owner", self.config.owner)
        Tags.of(self).add("DataClassification", "synthetic-student-data")

    def _create_network(self) -> None:
        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=self.config.nat_gateways,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="private-app",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="isolated-data",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )
        self.vpc.add_gateway_endpoint(
            "S3GatewayEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)],
        )

        self.alb_security_group = ec2.SecurityGroup(
            self,
            "AlbSecurityGroup",
            vpc=self.vpc,
            description="Public HTTPS ingress to the application load balancer",
            allow_all_outbound=True,
        )
        self.alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(443), "Public HTTPS"
        )
        self.alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv6(), ec2.Port.tcp(443), "Public HTTPS IPv6"
        )
        self.alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(80), "HTTP redirects to HTTPS"
        )
        self.alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv6(), ec2.Port.tcp(80), "HTTP redirects to HTTPS IPv6"
        )

        self.frontend_security_group = ec2.SecurityGroup(
            self,
            "FrontendSecurityGroup",
            vpc=self.vpc,
            description="Frontend accepts traffic only from the public ALB",
            allow_all_outbound=True,
        )
        self.frontend_security_group.add_ingress_rule(
            self.alb_security_group, ec2.Port.tcp(7860), "ALB to Gradio frontend"
        )

        self.api_security_group = ec2.SecurityGroup(
            self,
            "ApiSecurityGroup",
            vpc=self.vpc,
            description="API accepts ALB and frontend service traffic only",
            allow_all_outbound=True,
        )
        self.api_security_group.add_ingress_rule(
            self.alb_security_group, ec2.Port.tcp(8000), "ALB to FastAPI"
        )
        self.api_security_group.add_ingress_rule(
            self.frontend_security_group, ec2.Port.tcp(8000), "Frontend to internal FastAPI"
        )

        self.worker_security_group = ec2.SecurityGroup(
            self,
            "WorkerSecurityGroup",
            vpc=self.vpc,
            description="On-demand ingestion worker; no inbound connections",
            allow_all_outbound=True,
        )

        self.database_security_group = ec2.SecurityGroup(
            self,
            "DatabaseSecurityGroup",
            vpc=self.vpc,
            description="PostgreSQL accepts only API and ingestion worker traffic",
            allow_all_outbound=False,
        )
        self.database_security_group.add_ingress_rule(
            self.api_security_group, ec2.Port.tcp(5432), "API to PostgreSQL"
        )
        self.database_security_group.add_ingress_rule(
            self.worker_security_group, ec2.Port.tcp(5432), "Ingestion worker to PostgreSQL"
        )

        self.alb = elbv2.ApplicationLoadBalancer(
            self,
            "ApplicationLoadBalancer",
            vpc=self.vpc,
            internet_facing=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=self.alb_security_group,
            drop_invalid_header_fields=True,
            http2_enabled=True,
            deletion_protection=self.config.is_production,
        )

        self.certificate_arn = CfnParameter(
            self,
            "AcmCertificateArn",
            type="String",
            description=(
                "ARN of an ACM certificate in the stack Region, required for HTTPS. "
                "No certificate is created or looked up during synth."
            ),
        )
        certificate = acm.Certificate.from_certificate_arn(
            self, "ImportedCertificate", self.certificate_arn.value_as_string
        )
        self.https_listener = self.alb.add_listener(
            "HttpsListener",
            port=443,
            protocol=elbv2.ApplicationProtocol.HTTPS,
            certificates=[certificate],
            ssl_policy=elbv2.SslPolicy.TLS12_EXT,
            open=False,
        )
        self.http_listener = self.alb.add_listener(
            "HttpRedirectListener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_action=elbv2.ListenerAction.redirect(
                protocol="HTTPS", port="443", permanent=True
            ),
            open=False,
        )

    def _create_storage_and_database(self) -> None:
        self.artifact_key = kms.Key(
            self,
            "ArtifactEncryptionKey",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.RETAIN
            if self.config.is_production
            else RemovalPolicy.DESTROY,
            alias=f"alias/course-finder-{self.config.env_name}-artifacts",
        )
        self.artifact_key.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowApplicationLogs",
                principals=[iam.ServicePrincipal(f"logs.{self.region}.{self.url_suffix}")],
                actions=[
                    "kms:Encrypt",
                    "kms:Decrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:Describe*",
                ],
                resources=["*"],
                conditions={
                    "ArnEquals": {
                        "kms:EncryptionContext:aws:logs:arn": [
                            self.format_arn(
                                service="logs",
                                resource="log-group",
                                resource_name=f"/ecs/course-finder/{self.config.env_name}/{name}",
                                arn_format=ArnFormat.COLON_RESOURCE_NAME,
                            )
                            for name in ("frontend", "api", "ingestion-worker")
                        ]
                    }
                },
            )
        )
        self.bucket = s3.Bucket(
            self,
            "CourseMaterialsBucket",
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.artifact_key,
            bucket_key_enabled=True,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            removal_policy=RemovalPolicy.RETAIN
            if self.config.is_production
            else RemovalPolicy.DESTROY,
            auto_delete_objects=not self.config.is_production,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireNoncurrentVersions",
                    enabled=True,
                    noncurrent_version_expiration=Duration.days(
                        self.config.s3_noncurrent_retention_days
                    ),
                    abort_incomplete_multipart_upload_after=Duration.days(7),
                )
            ],
        )

        self.database = rds.DatabaseInstance(
            self,
            "PostgresDatabase",
            engine=rds.DatabaseInstanceEngine.postgres(version=rds.PostgresEngineVersion.VER_16_4),
            database_name="course_finder",
            credentials=rds.Credentials.from_generated_secret(
                username="course_finder",
                secret_name=f"course-finder/{self.config.env_name}/database",
            ),
            instance_type=ec2.InstanceType(self.config.database_instance_type),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED),
            security_groups=[self.database_security_group],
            publicly_accessible=False,
            storage_encrypted=True,
            allocated_storage=20,
            max_allocated_storage=100 if self.config.is_production else 50,
            backup_retention=Duration.days(self.config.backup_retention_days),
            preferred_backup_window="02:00-03:00",
            deletion_protection=self.config.is_production,
            multi_az=self.config.database_multi_az,
            cloudwatch_logs_exports=["postgresql"],
            cloudwatch_logs_retention=(
                logs.RetentionDays.ONE_MONTH
                if self.config.is_production
                else logs.RetentionDays.TWO_WEEKS
            ),
            copy_tags_to_snapshot=True,
            removal_policy=RemovalPolicy.RETAIN
            if self.config.is_production
            else RemovalPolicy.DESTROY,
        )
        if self.database.secret is None:
            raise RuntimeError("RDS must create a Secrets Manager credential secret")
        self.database_secret = self.database.secret
        self.database_secret.apply_removal_policy(
            RemovalPolicy.RETAIN if self.config.is_production else RemovalPolicy.DESTROY
        )
        self.session_secret = secretsmanager.Secret(
            self,
            "ApplicationSessionSecret",
            secret_name=f"course-finder/{self.config.env_name}/session",
            description="Server-side application signing/session secret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                password_length=64,
                exclude_punctuation=True,
            ),
            encryption_key=self.artifact_key,
            removal_policy=RemovalPolicy.RETAIN
            if self.config.is_production
            else RemovalPolicy.DESTROY,
        )

    def _create_identity(self) -> None:
        self.user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name=f"course-finder-{self.config.env_name}",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(username=True, email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
                temp_password_validity=Duration.days(3),
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            deletion_protection=self.config.is_production,
            removal_policy=RemovalPolicy.RETAIN
            if self.config.is_production
            else RemovalPolicy.DESTROY,
        )
        self.user_pool_client = self.user_pool.add_client(
            "ApplicationClient",
            user_pool_client_name=f"course-finder-{self.config.env_name}-app",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_srp=True, user_password=False),
            enable_token_revocation=True,
            prevent_user_existence_errors=True,
            access_token_validity=Duration.minutes(60),
            id_token_validity=Duration.minutes(60),
            refresh_token_validity=Duration.days(30),
        )
        self.role_groups = {
            role: cognito.CfnUserPoolGroup(
                self,
                f"{role.title()}RoleGroup",
                user_pool_id=self.user_pool.user_pool_id,
                group_name=role,
                description=(
                    f"Course Finder {role} role; application authorization remains server-enforced."
                ),
            )
            for role in ("student", "adviser", "admin")
        }

    def _create_repositories_and_cluster(self) -> None:
        repository_policy = (
            RemovalPolicy.RETAIN if self.config.is_production else RemovalPolicy.DESTROY
        )
        self.repositories = {
            name: ecr.Repository(
                self,
                f"{name.title()}Repository",
                repository_name=f"course-finder-{name}-{self.config.env_name}",
                image_scan_on_push=True,
                image_tag_mutability=ecr.TagMutability.IMMUTABLE,
                lifecycle_rules=[ecr.LifecycleRule(max_image_count=20, rule_priority=1)],
                empty_on_delete=not self.config.is_production,
                removal_policy=repository_policy,
            )
            for name in ("frontend", "api", "worker")
        }
        self.cluster = ecs.Cluster(
            self,
            "EcsCluster",
            vpc=self.vpc,
            cluster_name=f"course-finder-{self.config.env_name}",
            container_insights_v2=ecs.ContainerInsights.ENABLED,
        )
        self.namespace = self.cluster.add_default_cloud_map_namespace(
            name=f"course-finder-{self.config.env_name}.internal"
        )

    def _new_log_group(self, name: str) -> logs.LogGroup:
        return logs.LogGroup(
            self,
            f"{name.title()}LogGroup",
            log_group_name=f"/ecs/course-finder/{self.config.env_name}/{name}",
            retention=(
                logs.RetentionDays.ONE_MONTH
                if self.config.is_production
                else logs.RetentionDays.TWO_WEEKS
            ),
            encryption_key=self.artifact_key,
            removal_policy=RemovalPolicy.RETAIN
            if self.config.is_production
            else RemovalPolicy.DESTROY,
        )

    def _execution_role(
        self, name: str, repository: ecr.Repository, group: logs.LogGroup
    ) -> iam.Role:
        role = iam.Role(
            self,
            f"{name.title()}ExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description=(
                f"ECS execution role for {name}; pull its image and write its log stream only."
            ),
        )
        repository.grant_pull(role)
        group.grant_write(role)
        return role

    def _create_application_services(self) -> None:
        self.frontend_log_group = self._new_log_group("frontend")
        self.api_log_group = self._new_log_group("api")
        self.worker_log_group = self._new_log_group("ingestion-worker")
        image_tag = self.config.image_tag

        frontend_role = iam.Role(
            self,
            "FrontendTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Frontend has no direct AWS data or secret permissions.",
        )
        api_role = iam.Role(
            self,
            "ApiTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="API task role may read processed artifacts only.",
        )
        worker_role = iam.Role(
            self,
            "IngestionTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Ingestion task role accesses source and processed artifact prefixes.",
        )

        api_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:GetObjectVersion"],
                resources=[self.bucket.arn_for_objects("processed/*")],
            )
        )
        self.artifact_key.grant_decrypt(api_role)
        worker_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:GetObjectVersion"],
                resources=[
                    self.bucket.arn_for_objects("source/*"),
                    self.bucket.arn_for_objects("processed/*"),
                ],
            )
        )
        worker_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=[self.bucket.bucket_arn],
                conditions={
                    "StringLike": {
                        "s3:prefix": ["source/*", "processed/*"],
                    }
                },
            )
        )
        worker_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:AbortMultipartUpload"],
                resources=[self.bucket.arn_for_objects("processed/*")],
            )
        )
        self.artifact_key.grant_encrypt_decrypt(worker_role)
        frontend_task = ecs.FargateTaskDefinition(
            self,
            "FrontendTaskDefinition",
            cpu=512,
            memory_limit_mib=1024,
            task_role=frontend_role,
            execution_role=self._execution_role(
                "frontend", self.repositories["frontend"], self.frontend_log_group
            ),
        )
        frontend_container = frontend_task.add_container(
            "FrontendContainer",
            image=ecs.ContainerImage.from_ecr_repository(self.repositories["frontend"], image_tag),
            logging=ecs.LogDrivers.aws_logs(
                log_group=self.frontend_log_group, stream_prefix="frontend"
            ),
            environment={
                "APP_ENV": self.config.env_name,
                "UI_HOST": "0.0.0.0",
                "UI_PORT": "7860",
                "COURSE_FINDER_API_URL": (
                    f"http://api.course-finder-{self.config.env_name}.internal:8000"
                ),
            },
        )
        frontend_container.add_port_mappings(ecs.PortMapping(container_port=7860))

        api_execution_role = self._execution_role(
            "api", self.repositories["api"], self.api_log_group
        )
        self.database_secret.grant_read(api_execution_role)
        self.session_secret.grant_read(api_execution_role)
        api_task = ecs.FargateTaskDefinition(
            self,
            "ApiTaskDefinition",
            cpu=512,
            memory_limit_mib=1024,
            task_role=api_role,
            execution_role=api_execution_role,
        )
        api_container = api_task.add_container(
            "ApiContainer",
            image=ecs.ContainerImage.from_ecr_repository(self.repositories["api"], image_tag),
            logging=ecs.LogDrivers.aws_logs(log_group=self.api_log_group, stream_prefix="api"),
            environment={
                "APP_ENV": self.config.env_name,
                "AUTH_PROVIDER": "cognito",
                "AWS_REGION": self.region,
                "COGNITO_USER_POOL_ID": self.user_pool.user_pool_id,
                "COGNITO_CLIENT_ID": self.user_pool_client.user_pool_client_id,
                "S3_DOCUMENT_BUCKET": self.bucket.bucket_name,
                "DATA_ROOT": "/app/data",
                "DATABASE_HOST": self.database.db_instance_endpoint_address,
                "DATABASE_PORT": "5432",
                "DATABASE_NAME": "course_finder",
                "DATABASE_SECRET_ARN": self.database_secret.secret_arn,
            },
            secrets={
                "DATABASE_CREDENTIALS": ecs.Secret.from_secrets_manager(self.database_secret),
                "SESSION_SECRET": ecs.Secret.from_secrets_manager(self.session_secret),
            },
        )
        api_container.add_port_mappings(ecs.PortMapping(container_port=8000))

        worker_execution_role = self._execution_role(
            "ingestion-worker", self.repositories["worker"], self.worker_log_group
        )
        self.database_secret.grant_read(worker_execution_role)
        worker_task = ecs.FargateTaskDefinition(
            self,
            "IngestionTaskDefinition",
            cpu=1024,
            memory_limit_mib=4096,
            task_role=worker_role,
            execution_role=worker_execution_role,
        )
        worker_task.add_container(
            "IngestionWorkerContainer",
            image=ecs.ContainerImage.from_ecr_repository(self.repositories["worker"], image_tag),
            logging=ecs.LogDrivers.aws_logs(
                log_group=self.worker_log_group, stream_prefix="ingestion-worker"
            ),
            environment={
                "APP_ENV": self.config.env_name,
                "S3_DOCUMENT_BUCKET": self.bucket.bucket_name,
                "S3_SOURCE_PREFIX": "source/",
                "S3_PROCESSED_PREFIX": "processed/",
                "DATABASE_HOST": self.database.db_instance_endpoint_address,
                "DATABASE_PORT": "5432",
                "DATABASE_NAME": "course_finder",
                "DATABASE_SECRET_ARN": self.database_secret.secret_arn,
            },
            secrets={
                "DATABASE_CREDENTIALS": ecs.Secret.from_secrets_manager(self.database_secret),
            },
        )

        service_subnets = ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        self.frontend_service = ecs.FargateService(
            self,
            "FrontendService",
            cluster=self.cluster,
            service_name=f"course-finder-frontend-{self.config.env_name}",
            task_definition=frontend_task,
            desired_count=self.config.desired_count,
            assign_public_ip=False,
            security_groups=[self.frontend_security_group],
            vpc_subnets=service_subnets,
            cloud_map_options=ecs.CloudMapOptions(name="frontend"),
            enable_execute_command=False,
            min_healthy_percent=100,
            max_healthy_percent=200,
        )
        self.api_service = ecs.FargateService(
            self,
            "ApiService",
            cluster=self.cluster,
            service_name=f"course-finder-api-{self.config.env_name}",
            task_definition=api_task,
            desired_count=self.config.desired_count,
            assign_public_ip=False,
            security_groups=[self.api_security_group],
            vpc_subnets=service_subnets,
            cloud_map_options=ecs.CloudMapOptions(name="api"),
            enable_execute_command=False,
            min_healthy_percent=100,
            max_healthy_percent=200,
        )
        self.worker_task_definition = worker_task

        self.https_listener.add_targets(
            "FrontendTargets",
            port=7860,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[self.frontend_service],
            health_check=elbv2.HealthCheck(
                path="/", healthy_http_codes="200-399", interval=Duration.seconds(30)
            ),
        )
        self.https_listener.add_targets(
            "ApiTargets",
            priority=10,
            conditions=[elbv2.ListenerCondition.path_patterns(["/api/*"])],
            port=8000,
            protocol=elbv2.ApplicationProtocol.HTTP,
            targets=[self.api_service],
            health_check=elbv2.HealthCheck(
                path="/health", healthy_http_codes="200", interval=Duration.seconds(30)
            ),
        )

    def _create_observability(self) -> None:
        period = Duration.minutes(5)
        self.alarms: list[cloudwatch.Alarm] = []
        for name, service in (
            ("Frontend", self.frontend_service),
            ("Api", self.api_service),
        ):
            self.alarms.append(
                cloudwatch.Alarm(
                    self,
                    f"{name}CpuAlarm",
                    metric=service.metric_cpu_utilization(period=period),
                    threshold=80,
                    evaluation_periods=3,
                    datapoints_to_alarm=2,
                    comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                    treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
                    alarm_description=f"{name} ECS service CPU utilization is high.",
                )
            )
        self.alarms.extend(
            [
                cloudwatch.Alarm(
                    self,
                    "Alb5xxAlarm",
                    metric=self.alb.metrics.http_code_elb(
                        code=elbv2.HttpCodeElb.ELB_5XX_COUNT, period=period
                    ),
                    threshold=5,
                    evaluation_periods=2,
                    comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                    treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
                    alarm_description="ALB has elevated 5xx responses.",
                ),
                cloudwatch.Alarm(
                    self,
                    "DatabaseCpuAlarm",
                    metric=self.database.metric_cpu_utilization(period=period),
                    threshold=80,
                    evaluation_periods=3,
                    datapoints_to_alarm=2,
                    comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                    treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
                    alarm_description="RDS PostgreSQL CPU utilization is high.",
                ),
                cloudwatch.Alarm(
                    self,
                    "DatabaseStorageAlarm",
                    metric=self.database.metric_free_storage_space(period=period),
                    threshold=2 * 1024 * 1024 * 1024,
                    evaluation_periods=2,
                    comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
                    treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
                    alarm_description="RDS PostgreSQL free storage is below 2 GiB.",
                ),
            ]
        )

    def _create_outputs(self) -> None:
        CfnOutput(self, "LoadBalancerDnsName", value=self.alb.load_balancer_dns_name)
        CfnOutput(self, "S3BucketName", value=self.bucket.bucket_name)
        CfnOutput(self, "DatabaseEndpoint", value=self.database.db_instance_endpoint_address)
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)
        CfnOutput(self, "FrontendEcrUri", value=self.repositories["frontend"].repository_uri)
        CfnOutput(self, "ApiEcrUri", value=self.repositories["api"].repository_uri)
        CfnOutput(self, "WorkerEcrUri", value=self.repositories["worker"].repository_uri)
        CfnOutput(
            self,
            "IngestionWorkerSecurityGroupId",
            value=self.worker_security_group.security_group_id,
        )
        CfnOutput(
            self,
            "PrivateApplicationSubnetIds",
            value=",".join(
                subnet.subnet_id
                for subnet in self.vpc.select_subnets(
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
                ).subnets
            ),
            description=(
                "Use these subnets and the worker security group when invoking the Fargate task."
            ),
        )
