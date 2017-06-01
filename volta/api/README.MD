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



