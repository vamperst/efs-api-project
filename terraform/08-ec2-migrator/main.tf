resource "aws_security_group" "migrator" {
  name        = "${var.project}-migrator-sg"
  description = "EC2 migrator EFS->S3 (via Mountpoint)"
  vpc_id      = local.vpc_id

  egress {
    description = "Saida para EFS/S3/SSM/pkg repos"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.project}-migrator-sg" })
}

resource "aws_security_group_rule" "efs_from_migrator" {
  type                     = "ingress"
  from_port                = 2049
  to_port                  = 2049
  protocol                 = "tcp"
  security_group_id        = local.efs_sg_id
  source_security_group_id = aws_security_group.migrator.id
  description              = "NFS do migrator"
}

locals {
  efs_source = var.dataset_subpath == "" ? "/mnt/efs" : "/mnt/efs/${var.dataset_subpath}"
  s3_dest    = var.s3_subpath == "" ? "/mnt/s3" : "/mnt/s3/${var.s3_subpath}"

  # user-data:
  #   1) SSM agent
  #   2) CloudWatch Agent (metricas host + tail de /var/log/migrator/*)
  #   3) amazon-efs-utils + monta EFS (ro) em /mnt/efs via access point
  #   4) mount-s3 + monta bucket S3 em /mnt/s3 (uid/gid default, caching local)
  #   5) Script /usr/local/bin/migrate.sh que:
  #       - lista diretorios de primeiro nivel e paraleliza rsync
  #       - loga JSON estruturado em /var/log/migrator/migrate.jsonl
  #       - publica metricas EMF em /var/log/migrator/metrics.jsonl
  #       - no final, upload do JSON de resultado em s3://<bench-results>/results/migrator/<run_id>.json
  user_data = <<-EOT
    #!/bin/bash
    set -euxo pipefail
    exec > >(tee /var/log/migrator-user-data.log) 2>&1

    ### 1) SSM agent ###
    dnf upgrade -y amazon-ssm-agent || dnf install -y amazon-ssm-agent
    systemctl enable --now amazon-ssm-agent

    ### 2) Dependencias ###
    dnf install -y amazon-efs-utils awscli tmux rsync fuse fuse-libs \
                   python3 python3-pip jq

    ### 3) Monta EFS (ro) ###
    mkdir -p /mnt/efs
    grep -q "/mnt/efs" /etc/fstab || cat >> /etc/fstab <<EOF
    ${local.efs_file_system_id} /mnt/efs efs _netdev,tls,iam,accesspoint=${local.efs_ap_id},ro 0 0
    EOF
    mount -a -t efs || mount -t efs -o tls,iam,accesspoint=${local.efs_ap_id},ro ${local.efs_file_system_id}: /mnt/efs
    echo "EFS montado (ro):"; df -h /mnt/efs

    ### 4) Mountpoint for S3 ###
    if ! command -v mount-s3 >/dev/null; then
      curl -fsSL https://s3.amazonaws.com/mountpoint-s3-release/latest/x86_64/mount-s3.rpm -o /tmp/mount-s3.rpm
      dnf install -y /tmp/mount-s3.rpm
    fi
    mount-s3 --version

    mkdir -p /mnt/s3
    cat > /etc/systemd/system/mount-s3.service <<'UNIT'
    [Unit]
    Description=Mountpoint for Amazon S3 - ${local.s3files_bucket}
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=forking
    User=root
    ExecStart=/usr/bin/mount-s3 \\
      --allow-other --allow-delete --allow-overwrite \\
      --dir-mode 0755 --file-mode 0644 \\
      --region ${var.aws_region} \\
      ${local.s3files_bucket} /mnt/s3
    ExecStop=/bin/umount /mnt/s3
    Restart=on-failure
    RestartSec=10

    [Install]
    WantedBy=multi-user.target
    UNIT
    systemctl daemon-reload
    systemctl enable --now mount-s3.service

    # aguarda montar
    for i in $(seq 1 30); do
      mountpoint -q /mnt/s3 && { echo "S3 montado em /mnt/s3"; break; }
      sleep 2
    done

    ### 5) CloudWatch Agent ###
    dnf install -y amazon-cloudwatch-agent || true
    cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'CWA'
    {
      "agent": { "metrics_collection_interval": 30, "run_as_user": "root" },
      "metrics": {
        "namespace": "EfsS3Bench/Host",
        "append_dimensions": { "InstanceId": "$${aws:InstanceId}", "Role": "migrator" },
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
              { "file_path": "/var/log/migrator/migrate.jsonl", "log_group_name": "/bench/migrator", "log_stream_name": "{instance_id}/migrate.jsonl" },
              { "file_path": "/var/log/migrator/metrics.jsonl", "log_group_name": "/bench/migrator", "log_stream_name": "{instance_id}/metrics.jsonl" }
            ]
          }
        }
      }
    }
    CWA
    /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
      -a fetch-config -m ec2 -s \
      -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json || true

    mkdir -p /var/log/migrator && chown ec2-user:ec2-user /var/log/migrator

    ### 6) Script de migracao com observabilidade ###
    cat > /usr/local/bin/migrate.sh <<'MIG'
    #!/bin/bash
    set -euo pipefail
    SRC="$${1:-${local.efs_source}}"
    DST="$${2:-${local.s3_dest}}"
    PARALLEL="$${3:-${var.rsync_parallelism}}"

    # --- input validation (defense-in-depth contra chamadas via SSM send-command) ---
    # SRC SO pode estar em /mnt/efs, DST SO em /mnt/s3. Sem `..`, sem shell metachars.
    case "$$SRC" in
      /mnt/efs|/mnt/efs/*) ;;
      *) echo "ERRO: SRC deve comecar com /mnt/efs (recebido: $$SRC)" >&2; exit 2 ;;
    esac
    case "$$DST" in
      /mnt/s3|/mnt/s3/*) ;;
      *) echo "ERRO: DST deve comecar com /mnt/s3 (recebido: $$DST)" >&2; exit 2 ;;
    esac
    case "$$SRC$$DST" in
      *..*|*';'*|*'&'*|*'|'*|*'$$'*|*'`'*) echo "ERRO: caracteres invalidos em SRC/DST" >&2; exit 2 ;;
    esac
    case "$$PARALLEL" in
      ''|*[!0-9]*) echo "ERRO: PARALLEL deve ser inteiro" >&2; exit 2 ;;
    esac
    [[ "$$PARALLEL" -ge 1 && "$$PARALLEL" -le 32 ]] || { echo "ERRO: PARALLEL fora de [1,32]" >&2; exit 2; }

    RUN_ID=$$(uuidgen | tr -d '-' | cut -c1-12)
    LOG="/var/log/migrator/migrate.jsonl"
    METRICS="/var/log/migrator/metrics.jsonl"
    mkdir -p /var/log/migrator

    emit_log() {
      jq -cn \
        --arg ts "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --arg run "$$RUN_ID" \
        --arg msg "$$1" \
        --argjson fields "$${2:-{}}" \
        '{ts:$$ts, service:"migrator", run_id:$$run, msg:$$msg} * $$fields'
    }
    emit_metric() {
      # args: name value unit
      jq -cn \
        --arg run "$$RUN_ID" \
        --arg name "$$1" \
        --arg unit "$$3" \
        --argjson val $$2 \
        --argjson ts $$(date +%s000) \
        '{
          "_aws": {
            "Timestamp": $$ts,
            "CloudWatchMetrics": [{
              "Namespace": "$${METRIC_NAMESPACE:-EfsS3Bench}",
              "Dimensions": [["role","run_id"]],
              "Metrics": [{"Name": $$name, "Unit": $$unit}]
            }]
          },
          ($$name): $$val,
          "role": "migrator",
          "run_id": $$run
        }'
    }

    emit_log "migrate.start" "{\"src\":\"$$SRC\",\"dst\":\"$$DST\",\"parallel\":$$PARALLEL}" | tee -a "$$LOG"

    # prepara destino
    mkdir -p "$$DST"

    T_START=$$(date +%s.%N)

    # Lista diretorios de primeiro nivel da origem para paralelizar
    mapfile -t ENTRIES < <(find "$$SRC" -mindepth 1 -maxdepth 1 -printf '%f\n')
    if [ $${#ENTRIES[@]} -eq 0 ]; then
      emit_log "migrate.nothing_to_copy" '{}' | tee -a "$$LOG"
      exit 0
    fi

    # Executa rsync em paralelo (xargs -P). -a preserva perms/tempos.
    # --info=progress2 da progresso agregado.
    printf '%s\n' "$${ENTRIES[@]}" | \
      xargs -P "$$PARALLEL" -I{} bash -c '
        e="{}"
        t0=$$(date +%s.%N)
        # --inplace porque S3 via Mountpoint nao suporta rename
        rsync -a --inplace --no-compress --whole-file \
              "$$0/$$e/" "$$1/$$e/" 2>&1 || { echo "ERRO em $$e"; exit 99; }
        t1=$$(date +%s.%N)
        dur=$$(awk -v a="$$t1" -v b="$$t0" "BEGIN{print a-b}")
        bytes=$$(du -sb "$$1/$$e" 2>/dev/null | cut -f1 || echo 0)
        jq -cn --arg e "$$e" --argjson dur $$dur --argjson bytes $$bytes \
           "{ts:now|todate, service:\"migrator\", msg:\"migrate.entry_done\", entry:\$$e, duration_s:\$$dur, bytes:\$$bytes}"
      ' "$$SRC" "$$DST" | tee -a "$$LOG"

    T_END=$$(date +%s.%N)
    DURATION=$$(awk -v a="$$T_END" -v b="$$T_START" "BEGIN{print a-b}")
    TOTAL_BYTES=$$(du -sb "$$DST" 2>/dev/null | cut -f1 || echo 0)
    MBPS=$$(awk -v b="$$TOTAL_BYTES" -v d="$$DURATION" "BEGIN{print (b/1048576)/d}")

    emit_log "migrate.done" "{\"duration_s\":$$DURATION,\"bytes\":$$TOTAL_BYTES,\"mb_per_s\":$$MBPS}" | tee -a "$$LOG"
    emit_metric "MigrateThroughputMBps" $$MBPS "Megabytes/Second" >> "$$METRICS"
    emit_metric "MigrateBytes" $$TOTAL_BYTES "Bytes" >> "$$METRICS"
    emit_metric "MigrateDurationSeconds" $$DURATION "Seconds" >> "$$METRICS"

    # Upload do resultado agregado ao bucket de obs
    if [ -n "${local.bench_results_bucket}" ]; then
      RESULT=$$(jq -cn \
        --arg run "$$RUN_ID" \
        --arg src "$$SRC" --arg dst "$$DST" \
        --argjson duration $$DURATION \
        --argjson bytes $$TOTAL_BYTES \
        --argjson mbps $$MBPS \
        --arg started_at "$$(date -u -d @$$(printf '%.0f' $$T_START) +%Y-%m-%dT%H:%M:%SZ)" \
        --arg finished_at "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        '{run_id:$$run, service:"migrator", source:$$src, destination:$$dst, started_at:$$started_at, finished_at:$$finished_at, duration_s:$$duration, total_bytes:$$bytes, throughput_mb_per_s:$$mbps, status:"completed"}')
      echo "$$RESULT" | aws s3 cp - "s3://${local.bench_results_bucket}/results/migrator/$$RUN_ID.json" \
        --region ${var.aws_region} \
        --content-type application/json
    fi
    MIG
    chmod +x /usr/local/bin/migrate.sh

    echo "Migrator pronto. Origem: ${local.efs_source} -> Destino: ${local.s3_dest}"

    %{if var.auto_run_migration}
    sudo -u ec2-user tmux new-session -d -s mig "/usr/local/bin/migrate.sh"
    %{endif}
  EOT
}

resource "aws_instance" "migrator" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  subnet_id              = local.private_subnet_ids[0]
  vpc_security_group_ids = [aws_security_group.migrator.id]
  iam_instance_profile   = aws_iam_instance_profile.migrator.name
  ebs_optimized          = true

  user_data                   = local.user_data
  user_data_replace_on_change = true

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    http_endpoint               = "enabled"
  }

  root_block_device {
    volume_size           = 100
    volume_type           = "gp3"
    iops                  = 16000
    throughput            = 1000
    encrypted             = true
    delete_on_termination = true
  }

  monitoring = true

  tags = merge(local.common_tags, {
    Name = "${var.project}-migrator"
  })
}
