# Entry point
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


# Actual entry point
`volta-api`

# Usage samples
* start tests
```bash
curl 'http://localhost:9998/run' -XPOST --data \
'config={"volta":{"source":"/dev/cu.wchusbserial1420","type":"500hz","enabled":True}, "uplader": {"enabled": True, "task":"LOAD-272"}}' -v
```
* stop test
```bash
curl 'http://localhost:9998/stop?session=20170731173748_0000000000' -v
```
* status test
```bash
curl 'http://localhost:9998/status?session=20170731173748_0000000000' -v
```
