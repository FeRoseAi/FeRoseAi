# Documents Guide


## Build Guide
### ProtoBuf compile for gRPC
```shell
python -m grpc_tools.protoc -I./feroseai/pb --python_out=./feroseai/pb --grpc_python_out=./feroseai/pb feroseai.proto
```
