>**NOTE:** This is a [BlueOS Extension](https://blueos.cloud/docs/blueos/1.1/extensions/) for using the [Tailscale](https://tailscale.com/) service on a BlueOS device. It sets up a VPN to access your device from anywhere with an internet connection.
## Initial Setup

1. Install the Tailscale extension on your vehicle
1. [Download Tailscale](https://tailscale.com/download) on the device(s) you want to connect with, and log in
    - create an account if you haven't used Tailscale before
1. Open the Tailscale extension page in BlueOS and click **Log in**
    - a login link will appear; open it on any device (your phone or laptop is fine) and approve the vehicle
    - alternatively, expand **Use an auth key instead** and paste a key generated in the [Tailscale admin console](https://login.tailscale.com/admin/settings/keys)
      (useful for setting up many vehicles, or when the browser you're using can't reach the internet)
1. Once the status shows `Running`, the vehicle's Tailscale IP (`100.x.y.z`) and name are shown, along with the other devices on your tailnet
1. You should now be able to access the BlueOS web interface through the Tailscale connection
    - Use the **vehicle**'s Tailscale IP (e.g. `http://100.x.y.z`), or its MagicDNS name (e.g. `http://blueos`) if MagicDNS is enabled on your tailnet
    - SSH works the same as on the local network: `ssh pi@<vehicle-tailscale-ip>`
    - Connecting through Tailscale requires both ends of the connection to be logged in to the same tailnet and connected to the internet
1. Configure the desired endpoints (for MAVLink telemetry, video streams, serial, etc) to point to the intended recipient
    - Setting up a video stream requires setting up a stream endpoint for it in the [Video Streams](https://blueos.cloud/docs/blueos/1.1/advanced-usage/#video-streams) page
        - Creating a new stream endpoint while connected to BlueOS through the Tailscale connection will automatically use the connected **device**'s IP address
        - You can also get the relevant **device** IP address from the Peers table in the extension, or from the Tailscale admin console
    - Vehicle telemetry+control through QGroundControl is generally handled via a UDP Client link set up in BlueOS's [MAVLink Endpoints](https://blueos.cloud/docs/blueos/1.1/advanced-usage/#mavlink-endpoints) page, pointed at the **device**'s Tailscale IP
    - It is technically also possible to set up a MAVLink connection using BlueOS's GCS Server Link, by adding a "Comm Link" in QGroundControl to the **vehicle**'s Tailscale IP on port `14550`

### Recommended: disable key expiry

By default Tailscale requires devices to re-authenticate periodically. For a vehicle that may be deployed remotely, open the [Machines page](https://login.tailscale.com/admin/machines) of the admin console, open the vehicle's `...` menu and select **Disable key expiry**.

## Settings

- **Hostname on tailnet**: the vehicle's name in Tailscale and MagicDNS. Defaults to the BlueOS hostname.
- **Subnet routes**: advertise local networks (e.g. the tether network `192.168.2.0/24`) so tailnet devices can reach equipment behind the vehicle, such as IP cameras or sonars. After saving, approve the routes for the vehicle in the [Machines page](https://login.tailscale.com/admin/machines) (`...` → **Edit route settings**). Linux clients must also run `tailscale up --accept-routes`.

## General Usage

Once logged in, the vehicle reconnects automatically whenever it has internet access; the login is persisted across reboots and extension updates. Use **Log out** in the extension (or remove the machine in the admin console) to remove the vehicle from the tailnet.

## Troubleshooting

- `NeedsLogin`: the vehicle isn't logged in, or its key expired. Log in again, and consider disabling key expiry (see above)
- `NeedsMachineAuth`: your tailnet requires device approval; approve the vehicle in the admin console's Machines page
- If the connection isn't working, check that both devices show as connected in the [Machines page](https://login.tailscale.com/admin/machines), and look at the extension's **Health warnings**
- If the connection works but some endpoints don't, make sure they use the correct IP address
    - Something on the vehicle sending to a device (e.g. video, MAVLink UDP client) needs the **device**'s Tailscale IP
    - A device connecting to the vehicle (e.g. BlueOS web interface, GCS server link) needs the **vehicle**'s Tailscale IP or MagicDNS name
- Subnet devices unreachable: make sure the route is approved in the admin console and that the client accepts routes

## Advanced

Setting the `TS_AUTHKEY` environment variable on the container logs the vehicle in automatically on first start.
