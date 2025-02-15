provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-southeast-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t2.micro"
}

variable "ami_id" {
  description = "AMI ID for the EC2 instance"
  type        = string
  default     = "ami-0df7a207adb9748c7" # Amazon Linux 2023 AMI in ap-southeast-1
}

# IAM role for the Discord bot
resource "aws_iam_role" "discord_bot_role" {
  name = "discord-bot-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

# IAM policy for EC2 management
resource "aws_iam_role_policy" "ec2_management" {
  name = "ec2-management"
  role = aws_iam_role.discord_bot_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:StartInstances",
          "ec2:StopInstances",
          "cloudwatch:GetMetricData",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics"
        ]
        Resource = "*"
      }
    ]
  })
}

# IAM policy for RDS management
resource "aws_iam_role_policy" "rds_management" {
  name = "rds-management"
  role = aws_iam_role.discord_bot_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "rds:DescribeDBInstances",
          "rds:StartDBInstance",
          "rds:StopDBInstance",
          "cloudwatch:GetMetricData",
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:ListMetrics"
        ]
        Resource = "*"
      }
    ]
  })
}

# IAM policy for pricing API
resource "aws_iam_role_policy" "pricing_api" {
  name = "pricing-api"
  role = aws_iam_role.discord_bot_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "pricing:GetProducts",
          "pricing:DescribeServices"
        ]
        Resource = "*"
      }
    ]
  })
}

# IAM policy for SSM and CloudWatch
resource "aws_iam_role_policy" "ssm_policy" {
  name = "ssm-policy"
  role = aws_iam_role.discord_bot_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:UpdateInstanceInformation",
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel",
          "ec2messages:*"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "cloudwatch_policy" {
  name = "cloudwatch-policy"
  role = aws_iam_role.discord_bot_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "ec2:DescribeTags",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
          "logs:DescribeLogGroups",
          "logs:CreateLogStream",
          "logs:CreateLogGroup"
        ]
        Resource = "*"
      }
    ]
  })
}

# Instance profile for EC2 instances that need to assume this role
resource "aws_iam_instance_profile" "discord_bot_profile" {
  name = "discord-bot-profile"
  role = aws_iam_role.discord_bot_role.name
}

# VPC Configuration
resource "aws_vpc" "discord_bot_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "discord-bot-vpc"
  }
}

# Public Subnet
resource "aws_subnet" "public_subnet" {
  vpc_id                  = aws_vpc.discord_bot_vpc.id
  cidr_block             = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "${var.aws_region}a"

  tags = {
    Name = "discord-bot-public-subnet"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "discord_bot_igw" {
  vpc_id = aws_vpc.discord_bot_vpc.id

  tags = {
    Name = "discord-bot-igw"
  }
}

# Route Table
resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.discord_bot_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.discord_bot_igw.id
  }

  tags = {
    Name = "discord-bot-public-rt"
  }
}

# Route Table Association
resource "aws_route_table_association" "public_rt_assoc" {
  subnet_id      = aws_subnet.public_subnet.id
  route_table_id = aws_route_table.public_rt.id
}

# Security Group
resource "aws_security_group" "discord_bot_sg" {
  name        = "discord-bot-sg"
  description = "Security group for Discord bot EC2 instance"
  vpc_id      = aws_vpc.discord_bot_vpc.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "SSH access"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = {
    Name = "discord-bot-sg"
  }
}

# Key Pair
resource "aws_key_pair" "discord_bot_key" {
  key_name   = "discord-bot-key"
  public_key = file("~/.ssh/id_rsa.pub")  # Make sure this key exists
}

# EC2 Instance
resource "aws_instance" "discord_bot" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public_subnet.id
  vpc_security_group_ids = [aws_security_group.discord_bot_sg.id]
  key_name              = aws_key_pair.discord_bot_key.key_name
  iam_instance_profile  = aws_iam_instance_profile.discord_bot_profile.name

  user_data = <<-EOF
              #!/bin/bash
              yum update -y
              yum install -y python3-pip git

              # Install SSM Agent
              dnf install -y amazon-ssm-agent
              systemctl enable amazon-ssm-agent
              systemctl start amazon-ssm-agent

              # Install and configure CloudWatch agent
              yum install -y amazon-cloudwatch-agent
              
              # Configure CloudWatch agent
              cat <<'EOT' > /opt/aws/amazon-cloudwatch-agent/bin/config.json
              {
                "agent": {
                  "metrics_collection_interval": 60
                },
                "metrics": {
                  "metrics_collected": {
                    "mem": {
                      "measurement": [
                        "mem_used_percent",
                        "mem_available",
                        "mem_total",
                        "mem_used"
                      ],
                      "metrics_collection_interval": 60
                    }
                  }
                }
              }
              EOT

              # Start CloudWatch agent
              /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/bin/config.json
              systemctl enable amazon-cloudwatch-agent
              systemctl start amazon-cloudwatch-agent

              cd /home/ec2-user
              git clone https://github.com/your-repo/chatbot_discord.git
              cd chatbot_discord
              pip3 install -r requirements.txt

              # Create systemd service for the bot
              cat <<'EOT' > /etc/systemd/system/discord-bot.service
              [Unit]
              Description=Discord Bot Service
              After=network.target

              [Service]
              Type=simple
              User=ec2-user
              WorkingDirectory=/home/ec2-user/chatbot_discord
              ExecStart=/usr/bin/python3 main.py
              Restart=always
              RestartSec=3

              [Install]
              WantedBy=multi-user.target
              EOT

              systemctl daemon-reload
              systemctl enable discord-bot
              systemctl start discord-bot
              EOF

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    tags = {
      Name = "discord-bot-root-volume"
      Environment = "production"
      Service = "discord-bot"
      ManagedBy = "terraform"
    }
  }

  tags = {
    Name = "discord-bot"
  }
}

# Output the public IP of the EC2 instance
output "discord_bot_public_ip" {
  value = aws_instance.discord_bot.public_ip
}