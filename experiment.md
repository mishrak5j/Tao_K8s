Test #,Workload,Brain (Scheduler),What to watch for
5,YOLO (Batch),Bin-pack,Does it leave one node completely empty (Ready to be shut down)?
6,YOLO (Batch),Spread,"Does it pepper pods across both nodes, preventing ""Scale Down""?"
7,DLRM (Batch),Default,The baseline—how does standard K8s handle 10 small tasks?
8,DLRM (Batch),Bin-pack,"Does the ""Packing"" cause the disk I/O to slow down?"

Test #,Workload,Brain (Scheduler),What to watch for
9,ALL 4,Default,"Does one job ""Starve"" the others?"
10,ALL 4,Volcano,Does it handle the queue fairly?
11,ALL 4,Bin-pack,"Does the cluster ""Freeze"" because too many things are on one node?"
12,ALL 4,Spread,"Does it create ""Fragmentation"" where no ""Big"" job can fit anymore?"

Test #,Workload,Brain (Scheduler),What to watch for
1,ResNet (Dist),Volcano,"The ""Golden Standard""—all pods should start at once."
2,ResNet (Dist),Default,"Look for ""Partial Starts"" where the Master waits for a Worker."
3,BERT (Dist),Spread,Check if Network Latency increases because pods are far apart.
4,BERT (Dist),Bin-pack,Watch for Resource Contention (Master and Workers fighting for 1 GPU).