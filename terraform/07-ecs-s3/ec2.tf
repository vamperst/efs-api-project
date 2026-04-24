# EC2s que compoem o cluster ECS.
# O user-data:
#   1) registra a instancia no cluster ECS
#   2) instala mount-s3 (Mountpoint for Amazon S3)
#   3) monta o bucket em /mnt/s3 com perms tipo "posix" para uid/gid 1000
#      (mesmo uid do container da API)
#
# A task ECS depois faz um bind-mount de /mnt/s3 -> /mnt/efs dentro do container.
# Mantendo o mesmo mount path da API original.

locals {
  s3_mount_path = "/mnt/s3"

  user_data = <<-EOT
    #!/bin/bash
    set -euxo pipefail
    exec > >(tee /var/log/ecs-s3-user-data.log) 2>&1

    # 1) Registrar no cluster ECS
    echo "ECS_CLUSTER=${aws_ecs_cluster.this.name}" >> /etc/ecs/ecs.config
    echo "ECS_ENABLE_TASK_IAM_ROLE=true"            >> /etc/ecs/ecs.config
    echo "ECS_AVAILABLE_LOGGING_DRIVERS=[\"json-file\",\"awslogs\"]" >> /etc/ecs/ecs.config

    # 2) SSM agent (AL2023 ECS-optimized ja tras, so garantimos)
    dnf upgrade -y amazon-ssm-agent || dnf install -y amazon-ssm-agent
    systemctl enable --now amazon-ssm-agent

    # 3) Mountpoint for Amazon S3
    dnf install -y fuse fuse-libs || true
    if ! command -v mount-s3 >/dev/null; then
      curl -fsSL https://s3.amazonaws.com/mountpoint-s3-release/latest/x86_64/mount-s3.rpm -o /tmp/mount-s3.rpm
      dnf install -y /tmp/mount-s3.rpm
    fi
    mount-s3 --version

    # 4) CloudWatch Agent (metricas host: EBS IOPS, throughput, net, mem)
    dnf install -y amazon-cloudwatch-agent || true
    cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'CWA'
    {
      "agent": { "metrics_collection_interval": 30, "run_as_user": "root" },
      "metrics": {
        "namespace": "EfsS3Bench/Host",
        "append_dimensions": {
          "InstanceId": "$${aws:InstanceId}",
          "AutoScalingGroupName": "$${aws:AutoScalingGroupName}"
        },
        "metrics_collected": {
          "cpu":    { "measurement": ["cpu_usage_idle","cpu_usage_iowait","cpu_usage_user","cpu_usage_system"], "totalcpu": true },
          "mem":    { "measurement": ["mem_used_percent"] },
          "net":    { "measurement": ["bytes_sent","bytes_recv","packets_sent","packets_recv"], "resources": ["*"] },
          "disk":   { "measurement": ["used_percent","inodes_free"], "resources": ["/"], "drop_device": true },
          "diskio": { "measurement": ["reads","writes","read_bytes","write_bytes","io_time"], "resources": ["*"] }
        }
      }
    }
    CWA
    /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
      -a fetch-config -m ec2 -s \
      -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json || true

    # 5) Montagem persistente em ${local.s3_mount_path}
    mkdir -p ${local.s3_mount_path}

    # systemd unit para que o mount volte apos reboots
    cat > /etc/systemd/system/mount-s3.service <<'EOF'
    [Unit]
    Description=Mountpoint for Amazon S3 - bucket ${local.s3files_bucket}
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=forking
    User=root
    ExecStart=/usr/bin/mount-s3 \\
      --allow-other \\
      --allow-delete \\
      --uid 1000 --gid 1000 \\
      --dir-mode 0755 --file-mode 0644 \\
      --region ${var.aws_region} \\
      ${local.s3files_bucket} ${local.s3_mount_path}
    ExecStop=/bin/umount ${local.s3_mount_path}
    Restart=on-failure
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
    EOF

    systemctl daemon-reload
    systemctl enable --now mount-s3.service

    # Aguarda montar (ate 60s)
    for i in $(seq 1 30); do
      if mountpoint -q ${local.s3_mount_path}; then
        echo "S3 montado em ${local.s3_mount_path}"; break
      fi
      sleep 2
    done
  EOT
}

resource "aws_launch_template" "ecs" {
  name_prefix   = "${var.project}-s3-ecs-"
  image_id      = data.aws_ssm_parameter.ecs_ami.value
  instance_type = var.instance_type

  iam_instance_profile {
    name = aws_iam_instance_profile.ecs_instance.name
  }

  vpc_security_group_ids = [aws_security_group.ecs_instance.id]

  user_data = base64encode(local.user_data)

  # gp3 tunado para NAO ser gargalo no Mountpoint (cache local + FUSE overhead)
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 100
      volume_type           = "gp3"
      iops                  = 16000
      throughput            = 1000
      encrypted             = true
      delete_on_termination = true
    }
  }

  monitoring {
    enabled = true
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    http_endpoint               = "enabled"
  }

  tag_specifications {
    resource_type = "instance"
    tags = merge(local.common_tags, {
      Name = "${var.project}-s3-ecs-node"
    })
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_autoscaling_group" "ecs" {
  name                = "${var.project}-s3-ecs-asg"
  min_size            = var.asg_min
  max_size            = var.asg_max
  desired_capacity    = var.asg_desired
  vpc_zone_identifier = local.private_subnet_ids

  launch_template {
    id      = aws_launch_template.ecs.id
    version = "$Latest"
  }

  health_check_type         = "EC2"
  health_check_grace_period = 120

  tag {
    key                 = "Name"
    value               = "${var.project}-s3-ecs-node"
    propagate_at_launch = true
  }
  tag {
    key                 = "AmazonECSManaged"
    value               = "true"
    propagate_at_launch = true
  }

  lifecycle {
    create_before_destroy = true
    ignore_changes        = [desired_capacity]
  }
}

# Capacity Provider liga o ASG ao cluster ECS
resource "aws_ecs_capacity_provider" "asg" {
  name = "${var.project}-s3-asg-cp"

  auto_scaling_group_provider {
    auto_scaling_group_arn = aws_autoscaling_group.ecs.arn

    managed_scaling {
      status                    = "ENABLED"
      target_capacity           = 100
      minimum_scaling_step_size = 1
      maximum_scaling_step_size = 2
    }
  }

  tags = local.common_tags
}
