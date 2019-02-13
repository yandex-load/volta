



# HTTP API (concurrent tests, improved statuses)
Allows to start and stop test via HTTP interface.

Entry point: `volta-api`


Simply put config into a POST body.

Start test sample:
```bash
curl 'http://localhost:9998/api/v1/run' --data 'config={"volta":{"source":"/dev/cu.wchusbserial1420","type":"500hz","enabled":True}, "uploader": {"enabled": True, "task":"LOAD-272"},"phone":{"source":"1f434a75","type":"android","enabled":True}}' -v
```

Stop test sample:
```bash
curl 'http://localhost:9998/api/v1/stop?session=20170801180806_0000000000'
```

Check test status:
```bash
curl 'http://localhost:9998/api/v1/status?session=20170801180806_0000000000'
```


# Simple (another one) HTTP API, no concurrent tests allowed
`volta-http`

# Usage sample
* start test
```bash
curl 'http://localhost:9998/api/v1/start/' --data 'config={"volta":{"source":"/dev/cu.wchusbserial1420","type":"500hz"}}' -v
```
* stop test
```bash
curl 'http://localhost:9998/api/v1/stop/' -XPOST -v
```
