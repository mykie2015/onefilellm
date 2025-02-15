## onefilellm

+------------------------+     +-----------------------+
|      Input Source     |     |    Environment       |
|  (URL/Path/ID)        |     |    GITHUB_TOKEN      |
+------------------------+     +-----------------------+
           |                            |
           v                            v
+------------------------------------------------+
|              Source Type Detection              |
+------------------------------------------------+
           |
           v
+------------------+----------------------+
|                  |                      |
v                  v                      v
+------------+ +-----------+ +-------------------------+
|  GitHub    | |   Web     | |        Local           |
|  Sources   | |  Sources  | |        Files           |
+------------+ +-----------+ +-------------------------+
     |              |                    |
     v              v                    v
+------------+ +-----------+ +-------------------------+
| • Repos    | | • Docs    | | • Directory traversal   |
| • PRs      | | • ArXiv   | | • File filtering       |
| • Issues   | | • YouTube | | • Content extraction    |
+------------+ +-----------+ +-------------------------+
     |              |                    |
     v              v                    v
+------------------------------------------------+
|           File Type Validation                   |
| • Allowed extensions (.py,.md,.go,etc)          |
| • Excluded patterns (mocks,generated)            |
+------------------------------------------------+
           |
           v
+------------------------------------------------+
|           Content Processing                     |
| • XML structure creation                        |
| • Text extraction                               |
| • Code parsing                                  |
+------------------------------------------------+
           |
           v
+------------------------------------------------+
|           Output Generation                      |
| 1. uncompressed_output.txt                      |
| 2. compressed_output.txt (preprocessed)         |
| 3. Token counting                               |
| 4. Clipboard copy                               |
+------------------------------------------------+