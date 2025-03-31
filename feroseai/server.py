import grpc
import pickle
import ormsgpack
from typing import Optional
from logging import INFO, basicConfig, getLogger
from concurrent import futures
from omegaconf import OmegaConf
from dataclasses import dataclass
from .pb.froseai_pb2 import FeRoseAiMsg
from .pb.froseai_pb2_grpc import FeRoseAiServicer, add_FeRoseAiServicer_to_server
from .aggregator import AggAverage

formatter = '%(asctime)s [%(name)s] %(levelname)s :  %(message)s'
basicConfig(level=INFO, format=formatter)


@dataclass
class FeRoseAiParamsMsg:
    src: int
    params: bin
    status: int = 200
    round: int = 0
    metrics: Optional[dict] = None

@dataclass
class FeRoseAiPieceMsg:
    src: int
    status: int = 200
    round: int = 0

@dataclass
class FeRoseAiStsMsg:
    src: int
    status: int = 200
    round: int = 0
    metrics: Optional[dict] = None


class FeRoseAiGrpcGateway(FeRoseAiServicer):
    def __init__(self, config_pass: str, model, test_data=None, device="cpu"):
        self._agg = AggAverage(config_pass, model, test_data=test_data, device=device)
        self._logger = getLogger("FroseAi-Gateway")
        self._logger.info("Initialize!!")

    @property
    def model(self):
        return self._agg.model

    @property
    def metrics(self):
        return self._agg.metrics

    def Hello(self, request, context):
        self._agg.round = 1
        req = ormsgpack.unpackb(request.messages)
        ret_model_state = self.model.cpu().state_dict()
        if ret_model_state is None:
            params = request.messages
        else:
            params = {"model": ret_model_state}
        msg = FeRoseAiParamsMsg(src=req["src"], params=pickle.dumps(params), metrics=self.metrics, round=self._agg.round)
        return FeRoseAiMsg(messages=ormsgpack.packb(msg))

    def Push(self, request, context):
        req = ormsgpack.unpackb(request.messages)
        self._agg.push(req["src"], pickle.loads(req["params"]), req["round"])
        msg = FeRoseAiPieceMsg(src=req["src"], status=202)
        return FeRoseAiMsg(messages=ormsgpack.packb(msg))

    def Pull(self, request, context):
        status = 204
        messages = None
        req = ormsgpack.unpackb(request.messages)
        if not self._agg.snd_q[req["src"]].empty():
            status = 200
            messages = self._agg.snd_q[req["src"]].get()
            self._agg.clear_aggregator()

        msg = FeRoseAiParamsMsg(src=req["src"], status=status, params=messages, round=self._agg.round, metrics=self.metrics)
        return FeRoseAiMsg(messages=ormsgpack.packb(msg))

    def Status(self, request, context):
        req = ormsgpack.unpackb(request.messages)
        msg = FeRoseAiStsMsg(src=req["src"], status=200, round=self._agg.round, metrics=self.metrics)
        return FeRoseAiMsg(messages=ormsgpack.packb(msg))


class FeRoseAiServer:
    def __init__(self, config_pass: str, model, test_data=None, device="cpu", max_workers=4):
        self._conf = OmegaConf.load(config_pass)
        self._logger = getLogger("FroseAi-Srv")

        grpc_opts = [
            ("grpc.max_send_message_length", 1000 * 1024 * 1024),
            ("grpc.max_receive_message_length", 1000 * 1024 * 1024),
        ]
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers), options=grpc_opts, )
        self._servicer = FeRoseAiGrpcGateway(config_pass, model, test_data=test_data, device=device)

    def start(self):
        add_FeRoseAiServicer_to_server(self._servicer, self._server)
        port_num = int(self._conf.common.server_url.split(":")[1])
        port_str = '[::]:' + str(port_num)
        self._server.add_insecure_port(port_str)

        self._server.start()
        #self._server.wait_for_termination()
        self._logger.info("gPRC Server START : %s" % (port_str,))

    def stop(self):
        self._server.stop(grace=1)

