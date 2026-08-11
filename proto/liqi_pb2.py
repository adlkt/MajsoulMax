# liqi_pb2.py

from google.protobuf import descriptor_pb2
from google.protobuf import descriptor_pool
from google.protobuf import message_factory

pool = descriptor_pool.DescriptorPool()

fds = descriptor_pb2.FileDescriptorSet()

with open("./proto/liqi.desc", "rb") as f:
    fds.ParseFromString(f.read())

for file in fds.file:
    pool.Add(file)

factory = message_factory.MessageFactory(pool)

for file in fds.file:
    for message in file.message_type:
        descriptor = pool.FindMessageTypeByName(
            f"{file.package}.{message.name}"
        )
        # 兼容 protobuf 全版本：
        #   3.x: MessageFactory.GetPrototype(descriptor)
        #   4.x-6.x: MessageFactory.GetMessageClass(descriptor)
        #   7.x+: 实例方法被移除，改用模块级 message_factory.GetMessageClass(descriptor)
        get_class = (
            getattr(factory, "GetMessageClass", None)
            or getattr(factory, "GetPrototype", None)
            or message_factory.GetMessageClass
        )
        globals()[message.name] = get_class(descriptor)