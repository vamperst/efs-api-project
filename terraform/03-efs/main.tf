# Stack 02 - EFS
# EFS "padrao" (Standard, general purpose, bursting) + mount targets em cada
# subnet privada + access point em /data com uid/gid 1000 (batera com o user
# da API dentro do container).

# Security group do proprio EFS - permite NFS (2049) de dentro da VPC
resource "aws_security_group" "efs" {
  name        = "${var.project}-efs-sg"
  description = "Permite NFS (2049) de dentro da VPC para o EFS"
  vpc_id      = data.aws_vpc.this.id

  ingress {
    description = "NFS de dentro da VPC"
    from_port   = 2049
    to_port     = 2049
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.this.cidr_block]
  }

  egress {
    description = "Saida total (stateful)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project}-efs-sg"
  })
}

resource "aws_efs_file_system" "this" {
  creation_token   = "${var.project}-efs"
  performance_mode = "generalPurpose"

  # Elastic throughput: escalona automaticamente com a demanda.
  # Alternativa para benchmark com throughput conhecido seria "provisioned"
  # com throughput_in_mibps (mas Elastic eh o modo recomendado pela AWS
  # para workloads variaveis).
  # Ref: https://docs.aws.amazon.com/efs/latest/ug/performance.html
  # Atencao: depois de mudar para Elastic/Provisioned, a AWS impede
  # reduzir o throughput ou mudar modo por 24h.
  throughput_mode = var.throughput_mode
  # provisioned_throughput_in_mibps so eh valido quando throughput_mode=provisioned
  provisioned_throughput_in_mibps = var.throughput_mode == "provisioned" ? var.provisioned_throughput_mibps : null

  encrypted = true

  tags = merge(local.common_tags, {
    Name = "${var.project}-efs"
  })
}

resource "aws_efs_mount_target" "this" {
  count           = length(local.private_subnet_ids)
  file_system_id  = aws_efs_file_system.this.id
  subnet_id       = local.private_subnet_ids[count.index]
  security_groups = [aws_security_group.efs.id]
}

# Access point usado pela API e pela EC2 populator.
# root_directory /data criado automaticamente com uid/gid 1000 e perms 0755.
resource "aws_efs_access_point" "data" {
  file_system_id = aws_efs_file_system.this.id

  posix_user {
    uid = 1000
    gid = 1000
  }

  root_directory {
    path = "/data"
    creation_info {
      owner_uid   = 1000
      owner_gid   = 1000
      permissions = "0755"
    }
  }

  tags = merge(local.common_tags, {
    Name = "${var.project}-efs-ap-data"
  })
}
