import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class IncidentPayload:
    occurred_at_unix: int
    camera_id: str
    vehicle_class: str
    distance_m: float
    ttc_s: float
    severity_score: int
    severity_label: str
    alert_flag: bool
    clip_cid: str

    def to_contract_args(self) -> tuple:
        camera_hash = hashlib.sha256(self.camera_id.encode("utf-8")).hexdigest()
        camera_id_hash_hex = "0x" + camera_hash

        distance_cm = max(0, int(round(self.distance_m * 100)))
        ttc_ms = max(0, int(round(self.ttc_s * 1000)))
        score = max(0, min(100, int(self.severity_score)))

        return (
            int(self.occurred_at_unix),
            camera_id_hash_hex,
            self.vehicle_class,
            distance_cm,
            ttc_ms,
            score,
            self.severity_label,
            bool(self.alert_flag),
            self.clip_cid,
        )