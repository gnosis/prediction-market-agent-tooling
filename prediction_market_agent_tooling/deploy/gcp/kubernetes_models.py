from datetime import datetime
from typing import Any

from pydantic import BaseModel


class Metadata(BaseModel):
    creationTimestamp: datetime
    generation: int
    name: str
    namespace: str
    resourceVersion: str
    uid: str
    labels: dict[str, str]


class Metadata1(BaseModel):
    creationTimestamp: datetime | None
    name: str


class Metadata2(BaseModel):
    creationTimestamp: datetime | None
    name: str


class SecretKeyRef(BaseModel):
    key: str
    name: str
    optional: bool


class ValueFrom(BaseModel):
    secretKeyRef: SecretKeyRef


class EnvItem(BaseModel):
    name: str
    valueFrom: ValueFrom


class ConfigMapRef(BaseModel):
    name: str
    optional: bool


class EnvFromItem(BaseModel):
    configMapRef: ConfigMapRef


class Limits(BaseModel):
    cpu: str
    memory: str


class Requests(BaseModel):
    cpu: str
    memory: str


class Resources(BaseModel):
    limits: Limits
    requests: Requests


class Container(BaseModel):
    env: list[EnvItem]
    envFrom: list[EnvFromItem]
    image: str
    imagePullPolicy: str
    name: str
    resources: Resources
    terminationMessagePath: str
    terminationMessagePolicy: str


class NodeSelector(BaseModel):
    role: str


class Toleration(BaseModel):
    effect: str
    key: str
    operator: str
    value: str


class Spec2(BaseModel):
    automountServiceAccountToken: bool
    containers: list[Container]
    dnsPolicy: str
    enableServiceLinks: bool
    nodeSelector: NodeSelector
    restartPolicy: str
    schedulerName: str
    securityContext: dict[str, Any]
    shareProcessNamespace: bool
    terminationGracePeriodSeconds: int
    tolerations: list[Toleration]


class Template(BaseModel):
    metadata: Metadata2
    spec: Spec2


class Spec1(BaseModel):
    activeDeadlineSeconds: int
    backoffLimit: int
    completions: int
    manualSelector: bool
    parallelism: int
    template: Template


class JobTemplate(BaseModel):
    metadata: Metadata1
    spec: Spec1


class Spec(BaseModel):
    concurrencyPolicy: str
    failedJobsHistoryLimit: int
    jobTemplate: JobTemplate
    schedule: str
    successfulJobsHistoryLimit: int
    suspend: bool
    timeZone: str


class Status(BaseModel):
    lastScheduleTime: str | None = None
    lastSuccessfulTime: str | None = None


class KubernetesCronJob(BaseModel):
    apiVersion: str
    kind: str
    metadata: Metadata
    spec: Spec
    status: Status


class Metadata3(BaseModel):
    resourceVersion: str


class KubernetesCronJobsModel(BaseModel):
    apiVersion: str
    items: list[KubernetesCronJob]
    kind: str
    metadata: Metadata3
