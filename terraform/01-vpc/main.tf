# Stack 01 - VPC
# Baseado em: github.com/vamperst/fiap-arquitetura-compute-e-storage
# Evolucao: subnets privadas + NAT gateways (necessario para EFS/ECS privados)

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 3)
  common_tags = {
    env     = var.env
    project = var.project
  }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.common_tags, {
    Name = var.project
  })
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.this.id

  tags = merge(local.common_tags, {
    Name = "igw-${var.project}"
  })
}

# Subnets publicas
resource "aws_subnet" "public" {
  count                   = length(local.azs)
  vpc_id                  = aws_vpc.this.id
  cidr_block              = cidrsubnet(var.vpc_cidr, var.subnet_scale, count.index + 1)
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name = "${var.project}-public-${local.azs[count.index]}"
    Tier = "Public"
  })
}

# Subnets privadas (EFS mount targets + ECS + EC2 populator)
resource "aws_subnet" "private" {
  count             = length(local.azs)
  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.vpc_cidr, var.subnet_scale, count.index + 10)
  availability_zone = local.azs[count.index]

  tags = merge(local.common_tags, {
    Name = "${var.project}-private-${local.azs[count.index]}"
    Tier = "Private"
  })
}

# NAT Gateways (var.nat_count: 1=barato/sem-HA, length(azs)=HA por AZ)
resource "aws_eip" "nat" {
  count      = var.nat_count
  domain     = "vpc"
  depends_on = [aws_internet_gateway.igw]

  tags = merge(local.common_tags, {
    Name = "${var.project}-nat-eip-${local.azs[count.index]}"
  })
}

resource "aws_nat_gateway" "this" {
  count         = var.nat_count
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  depends_on = [aws_internet_gateway.igw]

  tags = merge(local.common_tags, {
    Name = "${var.project}-nat-${local.azs[count.index]}"
  })
}

# Route tables
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = merge(local.common_tags, {
    Name = "${var.project}-public-rt"
  })
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  count  = length(local.azs)
  vpc_id = aws_vpc.this.id

  # Se houver menos NATs que AZs, distribui round-robin (com 1 NAT, todas
  # apontam pro NAT unico). Com NAT por AZ, cada RT usa o NAT da sua AZ.
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[count.index % var.nat_count].id
  }

  tags = merge(local.common_tags, {
    Name = "${var.project}-private-rt-${local.azs[count.index]}"
    Tier = "Private"
  })
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}
