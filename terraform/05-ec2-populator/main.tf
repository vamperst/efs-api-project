resource "aws_security_group" "populator" {
  name        = "${var.project}-populator-sg"
  description = "EC2 populator do EFS"
  vpc_id      = local.vpc_id

  # Sem ingress - acesso via SSM Session Manager. SSH opcional se key_name estiver setada
  dynamic "ingress" {
    for_each = var.key_name == "" ? [] : [1]
    content {
      description = "SSH (usado so se key_name for fornecida)"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  egress {
    description = "Saida para SSM/EFS/pkg repos"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project}-populator-sg"
  })
}

# Permitir que o populator fale com o EFS via NFS
resource "aws_security_group_rule" "efs_from_populator" {
  type                     = "ingress"
  from_port                = 2049
  to_port                  = 2049
  protocol                 = "tcp"
  security_group_id        = local.efs_sg_id
  source_security_group_id = aws_security_group.populator.id
  description              = "NFS do populator"
}

# user-data: garante SSM agent funcional, instala efs-utils + python, monta EFS
locals {
  user_data = <<-EOT
    #!/bin/bash
    set -euxo pipefail
    exec > >(tee /var/log/populator-user-data.log) 2>&1

    echo "==> atualizando pacotes base"
    dnf makecache -y || true
    dnf install -y amazon-efs-utils python3 python3-pip unzip curl

    echo "==> garantindo amazon-ssm-agent instalado e atualizado"
    # AL2023 ja traz o agente. Garantimos que existe e esta na ultima versao.
    if ! rpm -q amazon-ssm-agent >/dev/null 2>&1; then
      dnf install -y amazon-ssm-agent || {
        # fallback: RPM oficial (caso o pacote nao esteja no repo padrao)
        curl -fsSL \
          "https://s3.${var.aws_region}.amazonaws.com/amazon-ssm-${var.aws_region}/latest/linux_amd64/amazon-ssm-agent.rpm" \
          -o /tmp/ssm-agent.rpm
        dnf install -y /tmp/ssm-agent.rpm
      }
    else
      dnf upgrade -y amazon-ssm-agent || true
    fi

    systemctl enable amazon-ssm-agent
    systemctl restart amazon-ssm-agent
    systemctl is-active --quiet amazon-ssm-agent && \
      echo "SSM agent ativo: $(rpm -q amazon-ssm-agent)"

    echo "==> instalando Faker + boto3 (usado pelo populate_efs.py)"
    pip3 install --quiet Faker boto3

    echo "==> CloudWatch Agent (metricas host + log tailing)"
    dnf install -y amazon-cloudwatch-agent || true
    cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'CWA'
    {
      "agent": { "metrics_collection_interval": 30, "run_as_user": "root" },
      "metrics": {
        "namespace": "EfsS3Bench/Host",
        "append_dimensions": { "InstanceId": "$${aws:InstanceId}", "Role": "populator" },
        "metrics_collected": {
          "cpu":    { "measurement": ["cpu_usage_idle","cpu_usage_iowait","cpu_usage_user","cpu_usage_system"], "totalcpu": true },
          "mem":    { "measurement": ["mem_used_percent"] },
          "net":    { "measurement": ["bytes_sent","bytes_recv"], "resources": ["*"] },
          "diskio": { "measurement": ["reads","writes","read_bytes","write_bytes","io_time"], "resources": ["*"] }
        }
      },
      "logs": {
        "logs_collected": {
          "files": {
            "collect_list": [
              { "file_path": "/var/log/populator/populate.jsonl", "log_group_name": "/bench/populator", "log_stream_name": "{instance_id}/populate.jsonl" }
            ]
          }
        }
      }
    }
    CWA
    /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
      -a fetch-config -m ec2 -s \
      -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json || true

    # Exporta env que o populate_efs.py usa para enviar resultado ao S3
    cat > /etc/profile.d/bench.sh <<EOF
    export BENCH_RESULTS_BUCKET="${local.bench_results_bucket}"
    export AWS_REGION="${var.aws_region}"
    export METRIC_NAMESPACE="EfsS3Bench"
    EOF
    mkdir -p /var/log/populator && chown ec2-user:ec2-user /var/log/populator

    echo "==> montando EFS via access point ${local.efs_ap_id}"
    mkdir -p /mnt/efs
    # fstab com access point + TLS + IAM auth
    grep -q "/mnt/efs" /etc/fstab || cat >> /etc/fstab <<EOF
    ${local.efs_file_system_id} /mnt/efs efs _netdev,tls,iam,accesspoint=${local.efs_ap_id} 0 0
    EOF
    mount -a -t efs || mount -t efs -o tls,iam,accesspoint=${local.efs_ap_id} ${local.efs_file_system_id}: /mnt/efs
    chown ec2-user:ec2-user /mnt/efs
    echo "EFS montado:"
    df -h /mnt/efs || true

    echo "==> pronto. Conecte via: aws ssm start-session --target <instance-id>"

    %{if var.auto_run_populator}
    # auto-run desabilitado por padrao - rode manualmente via populator/run_on_instance.sh
    %{endif}
  EOT
}

resource "aws_instance" "populator" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = local.private_subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.populator.id]
  iam_instance_profile   = aws_iam_instance_profile.populator.name
  key_name               = var.key_name == "" ? null : var.key_name
  ebs_optimized          = true

  user_data                   = local.user_data
  user_data_replace_on_change = true

  # Garante que os VPC endpoints do SSM (se habilitados) ja existem antes
  # da instancia subir - o agente tenta se registrar imediatamente.
  depends_on = [aws_vpc_endpoint.ssm]

  # gp3 tunado para NAO ser gargalo: 16k IOPS + 1000 MB/s de throughput.
  # 150 GiB de volume (dados ficam no EFS, o volume e so cache/scratch).
  root_block_device {
    volume_size           = 150
    volume_type           = "gp3"
    iops                  = 16000
    throughput            = 1000
    encrypted             = true
    delete_on_termination = true
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    http_endpoint               = "enabled"
  }

  # Monitoring detalhado do Nitro (metricas 1min em vez de 5min)
  monitoring = true

  tags = merge(local.common_tags, {
    Name = "${var.project}-populator"
    Role = "efs-populator"
  })
}
