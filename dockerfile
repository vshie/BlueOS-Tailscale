# vim: ft=dockerfile

FROM python:3.11-slim-bookworm AS stage

ARG PACKAGE_BASEURL=https://pkgs.tailscale.com/stable
ARG TAILSCALE_VERSION=1.104.4

COPY download.sh /download.sh
RUN chmod +x /download.sh && VERSION=${TAILSCALE_VERSION} /download.sh
FROM python:3.11-slim-bookworm

RUN apt-get update -qq && apt-get install -y --no-install-recommends iptables iproute2 ca-certificates procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=stage /tailscale-bin/tailscale /tailscale-bin/tailscaled /usr/local/bin/

COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

COPY web /web

RUN cd web && pip install .


LABEL version="1.104.4"
LABEL permissions='\
{\
    "NetworkMode":"host"\
    ,"HostConfig":{\
        "Privileged": true,\
        "NetworkMode":"host",\
        "CapAdd":["SYS_ADMIN","NET_ADMIN","NET_RAW"],\
        "Binds":["/usr/blueos/extensions/tailscale:/var/lib/tailscale"],\
        "Devices":[\
            {\
                "PathOnHost":"/dev/net/tun",\
                "PathInContainer":"/dev/net/tun",\
                "CgroupPermissions":"rwm"\
            }\
        ]\
    }\
} '
LABEL authors='[\
    {\
        "name": "Tony White",\
        "email": "tonywhite@bluerobotics.com"\
    }\
]'
LABEL company='{\
        "about": "",\
        "name": "Blue Robotics",\
        "email": "support@bluerobotics.com"\
    }'
LABEL type="other"
LABEL tags='[\
        "communication"\
    ]'
LABEL readme='https://raw.githubusercontent.com/vshie/BlueOS-Tailscale/{tag}/README.md'
LABEL links='{\
        "website": "https://github.com/vshie/BlueOS-Tailscale",\
        "support": "https://github.com/vshie/BlueOS-Tailscale/issues"\
    }'

LABEL requirements="core >= 1.1"


HEALTHCHECK --interval=10s CMD bash /healthcheck.sh


CMD []
ENTRYPOINT ["/entrypoint.sh"]
