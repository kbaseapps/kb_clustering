
import json
import os
import logging
import errno
import uuid
import sys
import pandas as pd

from installed_clients.DataFileUtilClient import DataFileUtil
from installed_clients.GenericsAPIClient import GenericsAPI
from installed_clients.kb_ke_utilClient import kb_ke_util
from installed_clients.KBaseReportClient import KBaseReport


class KmeansClusteringUtil:

    METRIC = ["braycurtis", "canberra", "chebyshev", "cityblock", "correlation", "cosine",
              "dice", "euclidean", "hamming", "jaccard", "kulsinski", "matching",
              "rogerstanimoto", "russellrao", "sokalmichener", "sokalsneath", "sqeuclidean",
              "yule"]

    def _mkdir_p(self, path):
        """
        _mkdir_p: make directory for given path
        """
        if not path:
            return
        try:
            os.makedirs(path)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            else:
                raise

    def _validate_run_kmeans_cluster_params(self, params):
        """
        _validate_run_kmeans_cluster_params:
                validates params passed to run_kmeans_cluster method
        """

        logging.info('start validating run_kmeans_cluster params')

        # check for required parameters
        for p in ['matrix_ref', 'workspace_name', 'cluster_set_name',
                  'k_num']:
            if p not in params:
                raise ValueError('"{}" parameter is required, but missing'.format(p))

        # check metric validation
        metric = params.get('dist_metric')
        if metric and metric not in self.METRIC:
            error_msg = 'INPUT ERROR:\nInput metric function [{}] is not valid.\n'.format(metric)
            error_msg += 'Available metric: {}'.format(self.METRIC)
            raise ValueError(error_msg)

    def _gen_clusters(self, clusters, conditionset_mapping):
        clusters_list = list()

        for cluster in list(clusters.values()):
            labeled_cluster = {}
            labeled_cluster.update({'id_to_data_position': cluster})
            if conditionset_mapping:
                id_to_condition = {k: v for k, v in list(conditionset_mapping.items()) if k in list(cluster.keys())}
                labeled_cluster.update({'id_to_condition': id_to_condition})

            clusters_list.append(labeled_cluster)

        return clusters_list

    def _build_kmeans_cluster_set(self, clusters, cluster_set_name, genome_ref, matrix_ref,
                                  conditionset_mapping, conditionset_ref, workspace_name,
                                  clustering_parameters):
        """
        _build_kmeans_cluster_set: build KBaseExperiments.ClusterSet object
        """

        logging.info('start saving KBaseExperiments.ClusterSet object')

        if isinstance(workspace_name, int) or workspace_name.isdigit():
            workspace_id = workspace_name
        else:
            workspace_id = self.dfu.ws_name_to_id(workspace_name)

        clusters_list = self._gen_clusters(clusters, conditionset_mapping)

        cluster_set_data = {'clusters': clusters_list,
                            'clustering_parameters': clustering_parameters,
                            'original_data': matrix_ref,
                            'condition_set_ref': conditionset_ref,
                            'genome_ref': genome_ref}

        cluster_set_data = {k: v for k, v in list(cluster_set_data.items()) if v}

        object_type = 'KBaseExperiments.ClusterSet'
        save_object_params = {
            'id': workspace_id,
            'objects': [{'type': object_type,
                         'data': cluster_set_data,
                         'name': cluster_set_name}]}

        dfu_oi = self.dfu.save_objects(save_object_params)[0]
        cluster_set_ref = str(dfu_oi[6]) + '/' + str(dfu_oi[0]) + '/' + str(dfu_oi[4])

        return cluster_set_ref

    def _build_kmeans_cluster(self, data_matrix, k_num, dist_metric=None):
        """
        _build_kmeans_cluster: Build Kmeans cluster
        """

        logging.info('start building clusters')

        # calculate distance matrix
        logging.info('start calculating distance matrix')
        pdist_params = {'data_matrix': data_matrix,
                        'metric': dist_metric}
        pdist_ret = self.ke_util.run_pdist(pdist_params)

        dist_matrix = pdist_ret['dist_matrix']
        # labels = pdist_ret['labels']

        # run kmeans algorithm
        logging.info('start performing Kmeans algorithm')
        kmeans_params = {'dist_matrix': dist_matrix,
                         'k_num': k_num}
        kmeans_ret = self.ke_util.run_kmeans2(kmeans_params)

        # centroid = kmeans_ret.get('kmeans_ret')
        idx = kmeans_ret.get('idx')

        df = pd.read_json(data_matrix)
        rows = df.index.tolist()

        clusters = {}
        for list_index, value in enumerate(idx):
            cluster = clusters.get(value)
            if not cluster:
                clusters.update({value: {rows[list_index]: list_index}})
            else:
                cluster.update({rows[list_index]: list_index})

        return clusters

    def _generate_kmeans_cluster_report(self, cluster_set_refs, workspace_name):
        """
        _generate_kmeans_cluster_report: generate summary report
        """
        objects_created = []
        for cluster_set_ref in cluster_set_refs:
            objects_created.append({'ref': cluster_set_ref,
                                    'description': 'Kmeans ClusterSet'})

        report_params = {'message': '',
                         'objects_created': objects_created,
                         'workspace_name': workspace_name,
                         'report_object_name': 'run_kmeans_cluster_' + str(uuid.uuid4())}

        kbase_report_client = KBaseReport(self.callback_url, token=self.token)
        output = kbase_report_client.create_extended_report(report_params)

        report_output = {'report_name': output['name'], 'report_ref': output['ref']}

        return report_output

    def __init__(self, config):
        self.ws_url = config["workspace-url"]
        self.callback_url = config['SDK_CALLBACK_URL']
        self.token = config['KB_AUTH_TOKEN']
        self.shock_url = config['shock-url']
        self.srv_wiz_url = config['srv-wiz-url']
        self.scratch = config['scratch']

        # helper kbase module
        self.dfu = DataFileUtil(self.callback_url)
        self.ke_util = kb_ke_util(self.callback_url, service_ver="dev")
        self.gen_api = GenericsAPI(self.callback_url, service_ver="dev")

        sys.setrecursionlimit(150000)

    def run_kmeans_cluster(self, params):
        """
        run_kmeans_cluster: generates Kmeans clusters for Matrix data object

        matrix_ref: Matrix object reference
        workspace_name: the name of the workspace
        cluster_set_name: KBaseExperiments.ClusterSet object name
        k_num: number of clusters to form

        Optional arguments:
        dist_metric: The distance metric to use. Default set to 'euclidean'.
                     The distance function can be
                     ["braycurtis", "canberra", "chebyshev", "cityblock", "correlation", "cosine",
                      "dice", "euclidean", "hamming", "jaccard", "kulsinski", "matching",
                      "rogerstanimoto", "russellrao", "sokalmichener", "sokalsneath", "sqeuclidean",
                      "yule"]
                     Details refer to:
                     https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.pdist.html

        return:
        cluster_set_refs: KBaseExperiments.ClusterSet object references
        report_name: report name generated by KBaseReport
        report_ref: report reference generated by KBaseReport
        """

        logging.info('--->\nrunning run_kmeans_cluster\n' +
                     'params:\n{}'.format(json.dumps(params, indent=1)))

        self._validate_run_kmeans_cluster_params(params)

        matrix_ref = params.get('matrix_ref')
        workspace_name = params.get('workspace_name')
        cluster_set_name = params.get('cluster_set_name')
        k_num = params.get('k_num')
        dist_metric = params.get('dist_metric')

        matrix_data = self.dfu.get_objects({'object_refs': [matrix_ref]})['data'][0]['data']

        data_matrix = self.gen_api.fetch_data({'obj_ref': matrix_ref}).get('data_matrix')
        transpose_data_matrix = pd.read_json(data_matrix).T.to_json()

        row_kmeans_clusters = self._build_kmeans_cluster(data_matrix, k_num,
                                                         dist_metric=dist_metric)

        col_kmeans_clusters = self._build_kmeans_cluster(transpose_data_matrix, k_num,
                                                         dist_metric=dist_metric)

        genome_ref = matrix_data.get('genome_ref')
        clustering_parameters = {'k_num': str(k_num),
                                 'dist_metric': str(dist_metric)}

        cluster_set_refs = []

        row_cluster_set_name = cluster_set_name + '_row'
        row_cluster_set = self._build_kmeans_cluster_set(
                                                    row_kmeans_clusters,
                                                    row_cluster_set_name,
                                                    genome_ref,
                                                    matrix_ref,
                                                    matrix_data.get('row_mapping'),
                                                    matrix_data.get('row_conditionset_ref'),
                                                    workspace_name,
                                                    clustering_parameters)
        cluster_set_refs.append(row_cluster_set)

        col_cluster_set_name = cluster_set_name + '_column'
        col_cluster_set = self._build_kmeans_cluster_set(
                                                    col_kmeans_clusters,
                                                    col_cluster_set_name,
                                                    genome_ref,
                                                    matrix_ref,
                                                    matrix_data.get('col_mapping'),
                                                    matrix_data.get('col_conditionset_ref'),
                                                    workspace_name,
                                                    clustering_parameters)
        cluster_set_refs.append(col_cluster_set)

        returnVal = {'cluster_set_refs': cluster_set_refs}

        report_output = self._generate_kmeans_cluster_report(cluster_set_refs, workspace_name)

        returnVal.update(report_output)

        return returnVal
