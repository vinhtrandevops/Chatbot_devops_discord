# Hướng dẫn Tạo và Sử dụng Discord Bot

## 1. Tạo Discord Bot
1. Truy cập [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" (góc phải trên)
3. Đặt tên cho bot (ví dụ: "bot đếp ốp xì nồ") và click "Create"
4. Trong menu bên trái, click vào "Bot"
5. Click "Add Bot" -> "Yes, do it!"
6. Trong phần "Privileged Gateway Intents":
   - Bật "MESSAGE CONTENT INTENT"
   - Click "Save Changes"
7. Copy Token:
   - Click "Reset Token"
   - Click "Yes, do it!"
   - Click "Copy" để copy token
   - Lưu token vào file `.env`
   
## 2. Tạo Link Mời Bot
1. Trong menu bên trái, click "OAuth2" -> "URL Generator"
2. Trong phần SCOPES, chọn:
   - [x] bot
   - [x] applications.commands
3. Trong phần BOT PERMISSIONS, chọn:
   - [x] Read Messages/View Channels
   - [x] Send Messages
   - [x] Read Message History
4. Copy URL được tạo ở dưới

## 3. Thêm Bot vào Server
1. Mở URL vừa copy trong trình duyệt
2. Chọn server từ dropdown "Add to Server"
3. Click "Continue"
4. Xem lại quyền và click "Authorize"
5. Hoàn thành captcha nếu có
6. Kiểm tra xem bot đã xuất hiện trong danh sách thành viên của server chưa

## 4. Sử Dụng Bot trong Discord

### Các Lệnh Cơ Bản
```
!list_servers     - Xem danh sách EC2 servers
!status           - Xem trạng thái tất cả EC2
!status bot-discord   - Xem trạng thái server cụ thể
!start bot-discord    - Khởi động EC2
!stop bot-discord     - Tắt EC2
```

### Cách Sử Dụng
1. Vào channel bất kỳ trong server
2. Gõ `!list_servers` để xem danh sách servers
3. Kiểm tra trạng thái:
   - `!status` để xem tất cả
   - `!status bot-discord` để xem server cụ thể
4. Khởi động server:
   - `!start bot-discord`
   - Đợi thông báo xác nhận
5. Tắt server:
   - `!stop bot-discord`
   - Đợi thông báo xác nhận

### Ý Nghĩa Các Icon
- Server đang chạy
- Server đã tắt
- Server đang khởi động
- Server đang tắt
- Server đã terminated
- Lỗi khi lấy trạng thái

### Xử Lý Lỗi Thường Gặp
1. Bot không phản hồi:
   - Kiểm tra bot có online không (chấm xanh)
   - Kiểm tra đã gõ đúng lệnh chưa (có dấu ! ở đầu)
   - Kiểm tra bot có quyền gửi tin nhắn trong channel không

2. Lệnh báo lỗi:
   - Kiểm tra cú pháp lệnh
   - Kiểm tra tên server có đúng không
   - Đọc thông báo lỗi để biết thêm chi tiết

3. Bot offline:
   - Kiểm tra container có đang chạy không
   - Xem logs để tìm nguyên nhân

## 🐳 Docker Guide

### Build và Run
```bash
# Build image
docker build -t discord-bot .

# Run container
docker run -d \
  --name discord-bot \
  --env-file .env \
  discord-bot
```

### Docker Compose
```yaml
version: '3.8'
services:
  bot:
    build: .
    env_file: .env
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Best Practices
1. **Base Image**: Sử dụng python:3.9-slim để giảm kích thước
2. **Multi-stage Build**: Tách biệt build và runtime
3. **Non-root User**: Chạy bot với user không có quyền root
4. **Health Check**: Kiểm tra bot có hoạt động không
5. **Logging**: Cấu hình log rotation

## 🔍 Troubleshooting Guide

### Các Lỗi Thường Gặp

1. **Bot Không Online**
   - Kiểm tra DISCORD_BOT_TOKEN
   - Xác nhận bot có quyền cần thiết
   - Check logs với `docker logs discord-bot`

2. **AWS API Errors**
   - Verify AWS credentials
   - Kiểm tra IAM permissions
   - Xác nhận region setting

3. **Rate Limits**
   - Implement exponential backoff
   - Sử dụng caching
   - Tối ưu số lượng API calls

### Debug Tips
```python
# Thêm debug logs
logger.debug(f'AWS Response: {response}')

# Test AWS credentials
boto3.client('sts').get_caller_identity()

# Verify Discord permissions
print(discord.utils.oauth_url(BOT_ID, permissions))
```

### FAQ

1. **Q**: Bot không phản hồi?
   **A**: Check permissions và command prefix

2. **Q**: AWS credentials không hoạt động?
   **A**: Verify credentials và region

3. **Q**: Rate limit Discord API?
   **A**: Implement cooldowns cho commands

## 📚 API Documentation

### AWS API

#### EC2 API Calls
```python
# Describe Instances
ec2.describe_instances(InstanceIds=[id])

# Start Instances
ec2.start_instances(InstanceIds=[id])

# Stop Instances
ec2.stop_instances(InstanceIds=[id])
```

#### Rate Limits
- AWS API: Tối đa 100 requests/giây
- Discord API: 50 messages/giây

#### Error Handling
```python
try:
    response = ec2.describe_instances()
except ClientError as e:
    if e.response['Error']['Code'] == 'ThrottlingException':
        # Implement backoff
    elif e.response['Error']['Code'] == 'UnauthorizedOperation':
        # Check permissions
```

## 🚀 Deployment Guide

### Production Deployment

1. **Chuẩn Bị**
   ```bash
   # Build production image
   docker build -t discord-bot:prod .
   
   # Push to registry
   docker push your-registry/discord-bot:prod
   ```

2. **Environment Setup**
   ```bash
   # Create secrets
   kubectl create secret generic discord-bot-secrets \
     --from-file=.env
   ```

3. **Deploy to Kubernetes**
   ```yaml
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: discord-bot
   spec:
     replicas: 1
     template:
       spec:
         containers:
         - name: bot
           image: discord-bot:prod
           envFrom:
           - secretRef:
               name: discord-bot-secrets
   ```

### CI/CD Pipeline

```yaml
name: Deploy Bot

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Build
      run: docker build -t discord-bot .
    - name: Test
      run: python -m pytest
    - name: Deploy
      run: |
        docker push your-registry/discord-bot
        kubectl apply -f k8s/
```

### Monitoring

1. **Metrics**
   - Command usage
   - API latency
   - Error rates

2. **Alerts**
   - Bot offline
   - High error rate
   - API throttling

## 👨‍💻 Development Guide

### Thêm Lệnh Mới

1. **Tạo Command**
```python
@bot.command()
async def new_command(ctx):
    """Command description"""
    logger.info(f'Command: new_command | User: {ctx.author}')
    # Command logic
    await add_success_reaction(ctx)
```

2. **Add Help Info**
```python
commands_info = {
    "new_command": {
        "description": "Mô tả lệnh",
        "usage": "!new_command <param>",
        "example": "!new_command test"
    }
}
```

### Code Style Guide

1. **Formatting**
   - Follow PEP 8
   - Use black formatter
   - Max line length: 88

2. **Documentation**
   - Docstrings cho mọi function
   - Type hints
   - Inline comments khi cần

3. **Error Handling**
   - Try/except blocks
   - Meaningful error messages
   - Proper logging

### Testing

1. **Unit Tests**
```python
def test_get_instance_state():
    instance_id = "i-1234567890"
    state, instance = get_instance_state(instance_id)
    assert state in ['running', 'stopped']
```

2. **Integration Tests**
```python
async def test_start_command():
    ctx = MockContext()
    await start(ctx, "test-server")
    assert ctx.message.reactions
```

3. **Mocking**
```python
@patch('boto3.client')
def test_aws_api(mock_client):
    mock_client.return_value.describe_instances.return_value = {
        'Reservations': [{'Instances': [{'State': {'Name': 'running'}}]}]
    }
```

## 📊 Performance Monitoring

### Metrics to Monitor
1. **Bot Performance**
   - Command response time
   - Memory usage
   - CPU usage

2. **AWS Metrics**
   - API latency
   - Throttling events
   - Error rates

3. **Discord Metrics**
   - Message latency
   - Rate limits
   - Connection stability

### Logging Best Practices
1. **Structured Logging**
```python
logger.info('Command executed', extra={
    'command': 'start',
    'user': str(ctx.author),
    'server': server_name,
    'response_time': response_time
})
```

2. **Log Levels**
   - ERROR: Lỗi nghiêm trọng
   - WARNING: Vấn đề không nghiêm trọng
   - INFO: Thông tin general
   - DEBUG: Chi tiết debug

3. **Log Rotation**
   - Rotate logs hàng ngày
   - Nén logs cũ
   - Xóa logs sau 30 ngày

## 🔒 Security Guide

### Best Practices
1. **Credentials**
   - Không hard code credentials
   - Rotate keys định kỳ
   - Sử dụng secrets management

2. **Permissions**
   - Principle of least privilege
   - Regular audit
   - Role-based access

3. **Network**
   - Use HTTPS/SSL
   - Firewall rules
   - Rate limiting

### Security Checklist
- [ ] Secure environment variables
- [ ] Implement rate limiting
- [ ] Regular security updates
- [ ] Audit logging
- [ ] Input validation
- [ ] Error handling
- [ ] Secure dependencies

## 🤝 Contributing

### Development Process
1. Fork repository
2. Create feature branch
3. Commit changes
4. Create pull request

### Pull Request Guidelines
1. Clear description
2. Tests included
3. Documentation updated
4. Code style followed

### Code Review Process
1. Automated checks pass
2. Manual review by maintainers
3. Changes requested/approved
4. Merge to main

## 📞 Support

### Contact
- GitHub Issues
- Discord Server
- Email Support

### Community
- Discord Community
- Stack Overflow Tag
- GitHub Discussions

## 📄 License
MIT License - see LICENSE file

## 👥 Authors
Developed by Eastplayers

---

*Last updated: February 2025*

# Discord Bot for AWS Management

Discord bot để quản lý các EC2 và RDS instances trên AWS.

## Tính năng

### EC2 Commands
- `!ec2-list`: Liệt kê tất cả EC2 instances
- `!ec2-start <server_name>`: Khởi động EC2 instance
- `!ec2-stop <server_name>`: Tắt EC2 instance
- `!ec2-status <server_name>`: Kiểm tra trạng thái EC2 instance
- `!ec2-metrics <server_name>`: Xem metrics của EC2 instance

### RDS Commands
- `!rds-list`: Liệt kê tất cả RDS instances
- `!rds-start <server_name>`: Khởi động RDS instance (chỉ full control)
- `!rds-stop <server_name>`: Tắt RDS instance (chỉ full control)
- `!rds-status <server_name>`: Kiểm tra trạng thái RDS instance
- `!rds-metrics [server_name]`: Xem metrics của RDS instance (nếu không chỉ định server_name sẽ hiển thị tất cả)

### Support Commands
- `!help`: Hiển thị danh sách các lệnh có sẵn
- `!ping`: Kiểm tra bot còn hoạt động không

## Cài đặt

1. Clone repository
```bash
git clone <repository_url>
cd chatbot_discord
```

2. Cài đặt dependencies
```bash
pip install -r requirements.txt
```

3. Tạo file `.env` với các thông tin cần thiết:
```bash
DISCORD_TOKEN=your_discord_token
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=ap-southeast-1

# EC2 instances mapping
EC2_INSTANCES=server1:i-xxxxx,server2:i-yyyyy

# RDS instances mapping (full control vs metrics only)
RDS_FULL_CONTROL_INSTANCES=staging-db:db-xxxxx
RDS_METRICS_ONLY_INSTANCES=prod-db:db-yyyyy
```

4. Chạy bot
```bash
python main.py
```

## AWS IAM Permissions

Bot cần các quyền sau trên AWS:

### EC2 Permissions
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:StartInstances",
                "ec2:StopInstances"
            ],
            "Resource": "*"
        }
    ]
}
```

### RDS Permissions
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "rds:DescribeDBInstances",
                "rds:StartDBInstance",
                "rds:StopDBInstance"
            ],
            "Resource": "*"
        }
    ]
}
```

### CloudWatch Permissions (cho metrics)
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "cloudwatch:GetMetricStatistics"
            ],
            "Resource": "*"
        }
    ]
}
```

### Pricing API Permissions (cho RDS memory info)
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "pricing:GetProducts"
            ],
            "Resource": "*"
        }
    ]
}
```

## Development

### Project Structure
```
chatbot_discord/
├── src/
│   ├── aws/
│   │   ├── ec2.py      # EC2 management
│   │   └── rds.py      # RDS management
│   ├── bot/
│   │   └── commands.py # Discord commands
│   ├── utils/
│   │   └── logger.py   # Logging setup
│   └── config.py       # Configuration
├── .env                # Environment variables
├── main.py            # Entry point
└── requirements.txt    # Dependencies
```

### Logging
- Logs được lưu trong thư mục `logs/`
- Format: `[TIMESTAMP] [LEVEL] [MODULE] Message`

### Error Handling
- Tất cả AWS operations đều có try/catch
- Errors được log và thông báo cho user qua Discord

## Contributing
1. Fork repository
2. Tạo feature branch
3. Commit changes
4. Push to branch
5. Tạo Pull request

## License
MIT