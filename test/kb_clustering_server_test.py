# -*- coding: utf-8 -*-
import os
import time
import unittest
from configparser import ConfigParser
import shutil
import inspect

from kb_clustering.kb_clusteringImpl import kb_clustering
from kb_clustering.kb_clusteringServer import MethodContext
from kb_clustering.authclient import KBaseAuth as _KBaseAuth

from installed_clients.WorkspaceClient import Workspace
from installed_clients.DataFileUtilClient import DataFileUtil
from installed_clients.GenericsAPIClient import GenericsAPI


class kb_clusteringTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        token = os.environ.get('KB_AUTH_TOKEN', None)
        config_file = os.environ.get('KB_DEPLOYMENT_CONFIG', None)
        cls.cfg = {}
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items('kb_clustering'):
            cls.cfg[nameval[0]] = nameval[1]
        # Getting username from Auth profile for token
        authServiceUrl = cls.cfg['auth-service-url']
        auth_client = _KBaseAuth(authServiceUrl)
        user_id = auth_client.get_user(token)
        # WARNING: don't call any logging methods on the context object,
        # it'll result in a NoneType error
        cls.ctx = MethodContext(None)
        cls.ctx.update({'token': token,
                        'user_id': user_id,
                        'provenance': [
                            {'service': 'kb_clustering',
                             'method': 'please_never_use_it_in_production',
                             'method_params': []
                             }],
                        'authenticated': 1})
        cls.wsURL = cls.cfg['workspace-url']
        cls.wsClient = Workspace(cls.wsURL)
        cls.serviceImpl = kb_clustering(cls.cfg)
        cls.scratch = cls.cfg['scratch']
        cls.callback_url = os.environ['SDK_CALLBACK_URL']
        suffix = int(time.time() * 1000)
        cls.wsName = "test_ContigFilter_" + str(suffix)
        ret = cls.wsClient.create_workspace({'workspace': cls.wsName})
        cls.wsId = ret[0]
        cls.dfu = DataFileUtil(cls.callback_url)
        cls.gen_api = GenericsAPI(cls.callback_url, service_ver='dev')

        cls.prepare_data()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'wsName'):
            cls.wsClient.delete_workspace({'workspace': cls.wsName})
            print('Test workspace was deleted')

    def getImpl(self):
        return self.__class__.serviceImpl

    def getWsName(self):
        return self.__class__.wsName

    @classmethod
    def prepare_data(cls):
        # upload KBaseFeatureValues.ExpressionMatrix object
        workspace_id = cls.dfu.ws_name_to_id(cls.wsName)
        object_type = 'KBaseFeatureValues.ExpressionMatrix'
        expression_matrix_object_name = 'test_expression_matrix'
        expression_matrix_data = {'scale': 'log2',
                                  'type': 'level',
                                  'data': {'row_ids': ['gene_1', 'gene_2', 'gene_3'],
                                           'col_ids': ['condition_1', 'condition_2',
                                                       'condition_3', 'condition_4'],
                                           'values': [[0.1, 0.2, 0.3, 0.4],
                                                      [0.3, 0.4, 0.5, 0.6],
                                                      [None, None, None, None]]
                                           },
                                  'feature_mapping': {},
                                  'condition_mapping': {}}
        save_object_params = {
            'id': workspace_id,
            'objects': [{'type': object_type,
                         'data': expression_matrix_data,
                         'name': expression_matrix_object_name}]
        }

        dfu_oi = cls.dfu.save_objects(save_object_params)[0]
        cls.expression_matrix_ref = str(dfu_oi[6]) + '/' + str(dfu_oi[0]) + '/' + str(dfu_oi[4])

        # upload KBaseMatrices.ExpressionMatrix object
        matrix_file_name = 'test_import.xlsx'
        matrix_file_path = os.path.join(cls.scratch, matrix_file_name)
        shutil.copy(os.path.join('data', matrix_file_name), matrix_file_path)

        obj_type = 'ExpressionMatrix'
        params = {'obj_type': obj_type,
                  'matrix_name': 'test_ExpressionMatrix',
                  'workspace_name': cls.wsName,
                  'input_file_path': matrix_file_path,
                  'scale': 'raw'}
        gen_api_ret = cls.gen_api.import_matrix_from_excel(params)

        cls.matrix_obj_ref = gen_api_ret.get('matrix_obj_ref')

    def fail_run_kmeans_cluster(self, params, error, exception=ValueError,
                                contains=False):
        with self.assertRaises(exception) as context:
            self.getImpl().run_kmeans_cluster(self.ctx, params)
        if contains:
            self.assertIn(error, str(context.exception.args[0]))
        else:
            self.assertEqual(error, str(context.exception.args[0]))

    def fail_run_hierarchical_cluster(self, params, error, exception=ValueError,
                                      contains=False):
        with self.assertRaises(exception) as context:
            self.getImpl().run_hierarchical_cluster(self.ctx, params)
        if contains:
            self.assertIn(error, str(context.exception.args[0]))
        else:
            self.assertEqual(error, str(context.exception.args[0]))

    def check_run_cluster_output(self, ret):
        self.assertTrue('cluster_set_ref' in ret)
        self.assertTrue('report_name' in ret)
        self.assertTrue('report_ref' in ret)

    def start_test(self):
        testname = inspect.stack()[1][3]
        print(('\n*** starting test: ' + testname + ' **'))

    def test_bad_run_kmeans_cluster_params(self):
        self.start_test()
        invalidate_params = {'missing_matrix_ref': 'matrix_ref',
                             'workspace_id': 'workspace_id',
                             'cluster_set_name': 'cluster_set_name',
                             'k_num': 'k_num'}
        error_msg = '"matrix_ref" parameter is required, but missing'
        self.fail_run_kmeans_cluster(invalidate_params, error_msg)

    def test_bad_run_hierarchical_cluster_params(self):
        self.start_test()
        invalidate_params = {'missing_matrix_ref': 'matrix_ref',
                             'workspace_id': 'workspace_id',
                             'cluster_set_name': 'cluster_set_name'}
        error_msg = '"matrix_ref" parameter is required, but missing'
        self.fail_run_hierarchical_cluster(invalidate_params, error_msg)

        invalidate_params = {'matrix_ref': 'matrix_ref',
                             'missing_workspace_id': 'workspace_id',
                             'cluster_set_name': 'cluster_set_name'}
        error_msg = '"workspace_id" parameter is required, but missing'
        self.fail_run_hierarchical_cluster(invalidate_params, error_msg)

        invalidate_params = {'matrix_ref': 'matrix_ref',
                             'workspace_id': 'workspace_id',
                             'missing_cluster_set_name': 'cluster_set_name'}
        error_msg = '"cluster_set_name" parameter is required, but missing'
        self.fail_run_hierarchical_cluster(invalidate_params, error_msg)

        invalidate_params = {'matrix_ref': 'matrix_ref',
                             'workspace_id': 'workspace_id',
                             'cluster_set_name': 'cluster_set_name',
                             'dist_cutoff_rate': 'dist_cutoff_rate',
                             'dist_metric': 'invalidate_metric'}
        error_msg = 'INPUT ERROR:\nInput metric function [invalidate_metric] is not valid.\n'
        self.fail_run_hierarchical_cluster(invalidate_params, error_msg, contains=True)

        invalidate_params = {'matrix_ref': 'matrix_ref',
                             'workspace_id': 'workspace_id',
                             'cluster_set_name': 'cluster_set_name',
                             'dist_cutoff_rate': 'dist_cutoff_rate',
                             'linkage_method': 'invalidate_method'}
        error_msg = "INPUT ERROR:\nInput linkage algorithm [invalidate_method] is not valid.\n"
        self.fail_run_hierarchical_cluster(invalidate_params, error_msg, contains=True)

        invalidate_params = {'matrix_ref': 'matrix_ref',
                             'workspace_id': 'workspace_id',
                             'cluster_set_name': 'cluster_set_name',
                             'dist_cutoff_rate': 'dist_cutoff_rate',
                             'fcluster_criterion': 'invalidate_criterion'}
        error_msg = "INPUT ERROR:\nInput criterion [invalidate_criterion] is not valid.\n"
        self.fail_run_hierarchical_cluster(invalidate_params, error_msg, contains=True)

    def test_run_kmeans_cluster(self):
        self.start_test()

        # test KBaseMatrices.ExpressionMatrix input
        params = {'matrix_ref': self.matrix_obj_ref,
                  'workspace_id': self.wsId,
                  'cluster_set_name': 'test_kmeans_cluster',
                  'k_num': 2}
        ret = self.getImpl().run_kmeans_cluster(self.ctx, params)[0]
        self.check_run_cluster_output(ret)

        # test KBaseFeatureValues.ExpressionMatrix input
        params = {'matrix_ref': self.expression_matrix_ref,
                  'workspace_id': self.wsId,
                  'cluster_set_name': 'test_kmeans_cluster',
                  'k_num': 3}
        ret = self.getImpl().run_kmeans_cluster(self.ctx, params)[0]
        self.check_run_cluster_output(ret)

    def test_run_hierarchical_cluster(self):
        self.start_test()

        # test KBaseMatrices.ExpressionMatrix input
        params = {'matrix_ref': self.matrix_obj_ref,
                  'workspace_id': self.wsId,
                  'cluster_set_name': 'test_hierarchical_cluster_1',
                  'dist_metric': 'euclidean',
                  'linkage_method': 'ward',
                  'fcluster_criterion': 'distance'}
        ret = self.getImpl().run_hierarchical_cluster(self.ctx, params)[0]
        self.check_run_cluster_output(ret)

        # test KBaseFeatureValues.ExpressionMatrix input
        params = {'matrix_ref': self.expression_matrix_ref,
                  'workspace_id': self.wsId,
                  'cluster_set_name': 'test_hierarchical_cluster_2',
                  'col_dist_cutoff_rate': 0.6,
                  'row_dist_cutoff_rate': 0.6,
                  'dist_metric': 'euclidean',
                  'linkage_method': 'single',
                  'fcluster_criterion': 'distance'}
        ret = self.getImpl().run_hierarchical_cluster(self.ctx, params)[0]
        self.check_run_cluster_output(ret)
