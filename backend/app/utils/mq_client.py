import pika
from app.config import settings


class MQClient:
    def __init__(self):
        self.connection = None
        self.channel = None

    def connect(self):
        """连接到RabbitMQ"""
        credentials = pika.PlainCredentials(settings.MQ_USER, settings.MQ_PASSWORD)
        parameters = pika.ConnectionParameters(
            host=settings.MQ_HOST,
            port=settings.MQ_PORT,
            virtual_host=settings.MQ_VHOST,
            credentials=credentials
        )
        self.connection = pika.BlockingConnection(parameters)
        self.channel = self.connection.channel()

    def declare_queue(self, queue_name: str, durable: bool = True):
        """声明队列"""
        if not self.channel:
            self.connect()
        self.channel.queue_declare(queue=queue_name, durable=durable)

    def send_message(self, queue_name: str, message: str):
        """发送消息"""
        if not self.channel:
            self.connect()
        self.channel.basic_publish(
            exchange='',
            routing_key=queue_name,
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)
        )

    def consume_messages(self, queue_name: str, callback):
        """消费消息"""
        if not self.channel:
            self.connect()
        self.channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
        self.channel.start_consuming()

    def close(self):
        """关闭连接"""
        if self.connection:
            self.connection.close()


mq_client = MQClient()
